"""
Unworking stub for doing transclusion in markdown.
"""

import re

from markdown.postprocessors import Postprocessor
from markdown.extensions import Extension

from tiddlyweb.control import determine_bag_from_recipe
from tiddlyweb.util import renderable
from tiddlyweb.store import StoreError
from tiddlyweb.model.bag import Bag
from tiddlyweb.model.policy import PermissionsError
from tiddlyweb.model.recipe import Recipe
from tiddlyweb.model.tiddler import Tiddler
from tiddlyweb.wikitext import render_wikitext

try:
    from tiddlywebplugins.tiddlyspace.spaces import space_uri
    TRANSCLUDE_RE = r'<p>{{([^}]+)}}(?:@([0-9a-z][0-9a-z\-]*[0-9a-z]))?</p>'
except ImportError:
    TRANSCLUDE_RE = re.compile(r'<p>{{([^}]+)}}</p>')

def get_bag_from_recipe(environ, recipe_name, tiddler):
    """
    Check recipe policy, determine which bag this tiddler
    ought to come from, and check that bag's policy too.
    Raises StoreError and PermissionsError.
    """
    store = environ['tiddlyweb.store']
    recipe = store.get(Recipe(recipe_name))
    recipe.policy.allows(environ['tiddlyweb.usersign'], 'read')
    bag = determine_bag_from_recipe(recipe, tiddler, environ)
    bag = store.get(Bag(bag.name))
    bag.policy.allows(environ['tiddlyweb.usersign'], 'read')
    return bag


class TranscludeProcessor(Postprocessor):

    def __init__(self, pattern, config):
        Postprocessor.__init__(self)
        self.pattern = pattern
        self.environ = config['environ']
        self.tiddler = config['tiddler']
        self.store = self.environ.get('tiddlyweb.store')
        self.transclude_stack = {}

    def transcluder(self, match):
        space_recipe = None
        interior_title = match.group(1)
        space = match.group(2)

        if space:
            space_recipe = '%s_public' % space

        # bail out if we are looping
        if interior_title in self.transclude_stack:
            return match.group(0)
        
        # bail out if we have no store
        if not self.store:
            return match.group(0)

        try:
            self.transclude_stack[self.tiddler.title].append(
                    interior_title)
        except KeyError:
            self.transclude_stack[self.tiddler.title] = [interior_title]

        interior_tiddler = Tiddler(interior_title)
        try:
            if space_recipe:
                interior_bag = get_bag_from_recipe(self.environ,
                        space_recipe, interior_tiddler)
                interior_tiddler.bag = interior_bag.name
            else:
                if self.tiddler.recipe:
                    interior_bag = get_bag_from_recipe(self.environ,
                            self.tiddler.recipe, interior_tiddler)
                    interior_tiddler.bag = interior_bag.name
                else:
                    interior_tiddler.bag = self.tiddler.bag
            interior_tiddler = self.store.get(interior_tiddler)
        except (StoreError, KeyError, PermissionsError):
            return match.group(0)

        if renderable(interior_tiddler, self.environ):
            content = render_wikitext(interior_tiddler, self.environ)
        else:
            content = ''
        return '<article class="transclusion" data-title="%s" ' \
                'data-bag="%s">%s</article>' % (interior_tiddler.title,
                        interior_tiddler.bag, content)

    def run(self, text):
        return re.sub(self.pattern, self.transcluder, text)


class TransclusionExtension(Extension):

    def __init__(self, configs):
        self.config = {
                'environ': [{}, 'TiddlyWeb WSGI environ'],
                'tiddler': [None, 'The tiddler being worked on']
        }
        for key, value in configs:
            self.setConfig(key, value)

    def extendMarkdown(self, md, md_globals):
        transcludeProcessor = TranscludeProcessor(TRANSCLUDE_RE,
                self.getConfigs())
        transcludeProcessor.md = md
        md.postprocessors['transclusion'] = transcludeProcessor


def makeExtension(configs=None):
    return TransclusionExtension(configs=configs)
