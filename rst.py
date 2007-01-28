#!/usr/bin/env python
#
# Natural Language Toolkit: Documentation generation script
#
# Copyright (C) 2001-2006 University of Pennsylvania
# Author: Edward Loper <edloper@gradient.cis.upenn.edu>
# URL: <http://nltk.sf.net>
# For license information, see LICENSE.TXT

r"""
This is a customized driver for converting docutils reStructuredText
documents into HTML and LaTeX.  It customizes the standard writers in
the following ways:
    
    - Source code highlighting is added to all doctest blocks.  In
      the HTML output, highlighting is performed using css classes:
      'pysrc-prompt', 'pysrc-keyword', 'pysrc-string', 'pysrc-comment',
      and 'pysrc-output'.  In the LaTeX output, highlighting uses five
      new latex commands: '\pysrcprompt', '\pysrckeyword',
      '\pysrcstring', '\pysrccomment', and '\pyrcoutput'.

    - A new "example" directive is defined.

    - A new "doctest-ignore" directive is defined.

    - A new "tree" directive is defined.

    - New directives "def", "ifdef", and "ifndef", which can be used
      to conditionally control the inclusion of sections.  This is
      used, e.g., to make sure that the definitions in 'definitions.txt'
      are only performed once, even if 'definitions.txt' is included
      multiple times.
"""

import re, os.path, textwrap, shelve
from optparse import OptionParser
from tree2image import tree_to_image

import docutils.core, docutils.nodes, docutils.io
from docutils.writers import Writer
from docutils.writers.html4css1 import HTMLTranslator, Writer as HTMLWriter
from docutils.writers.latex2e import LaTeXTranslator, Writer as LaTeXWriter
from docutils.parsers.rst import directives, roles
from docutils.readers.standalone import Reader as StandaloneReader
from docutils.transforms import Transform
import docutils.writers.html4css1

LATEX_VALIGN_IS_BROKEN = True
"""Set to true to compensate for a bug in the latex writer.  I've
   submitted a patch to docutils, so hopefully this wil be fixed
   soon."""

LATEX_DPI = 140
"""The scaling factor that should be used to display bitmapped images
   in latex/pdf output (specified in dots per inch).  E.g., if a
   bitmapped image is 100 pixels wide, it will be scaled to
   100/LATEX_DPI inches wide for the latex/pdf output.  (Larger
   values produce smaller images in the generated pdf.)"""

OUTPUT_FORMAT = None
"""A global variable, set by main(), indicating the output format for
   the current file.  Can be 'latex' or 'html' or 'ref'."""

OUTPUT_BASENAME = None
"""A global variable, set by main(), indicating the base filename
   of the current file (i.e., the filename with its extension
   stripped).  This is used to generate filenames for images."""

TREE_IMAGE_DIR = 'tree_images/'
"""The directory that tree images should be written to."""

EXTERN_REFERENCE_FILES = []
"""A list of .ref files, for crossrefering to external documents (used
   when building one chapter at a time)."""

BIBTEX_FILE = 'book.bib'
"""The name of the bibtex file used to generate bibliographic entries.
   """

BIBLIOGRAPHY_HTML = "bibliography.html"
"""The name of the HTML file containing the bibliography (for
   hyperrefs from citations)."""

LOCAL_BIBLIOGRAPHY = False
"""If true, assume that this document contains the bibliography, and
   link to it locally; if false, assume that bibliographic links
   should point to L{BIBLIOGRAPHY_HTML}."""

######################################################################
#{ Directives
######################################################################

class example(docutils.nodes.paragraph): pass

def example_directive(name, arguments, options, content, lineno,
                      content_offset, block_text, state, state_machine):
    """
    Basic use::

        .. example:: John went to the store.

    To refer to examples, use::

        .. _store:
        .. example:: John went to the store.

        In store_, John performed an action.
    """
    text = '\n'.join(content)
    node = example(text)
    state.nested_parse(content, content_offset, node)
    return [node]
example_directive.content = True
directives.register_directive('example', example_directive)
directives.register_directive('ex', example_directive)

def doctest_directive(name, arguments, options, content, lineno,
                      content_offset, block_text, state, state_machine):
    """
    Used to explicitly mark as doctest blocks things that otherwise
    wouldn't look like doctest blocks.
    """
    text = '\n'.join(content)
    if re.match(r'.*\n\s*\n', block_text):
        print ('WARNING: doctest-ignore on line %d will not be ignored, '
               'because there is\na blank line between ".. doctest-ignore::"'
               ' and the doctest example.' % lineno)
    return [docutils.nodes.doctest_block(text, text)]
doctest_directive.content = True
directives.register_directive('doctest-ignore', doctest_directive)

_treenum = 0
def tree_directive(name, arguments, options, content, lineno,
		   content_offset, block_text, state, state_machine):
    global _treenum
    text = '\n'.join(arguments) + '\n'.join(content)
    _treenum += 1
    # Note: the two filenames generated by these two cases should be
    # different, to prevent conflicts.
    if OUTPUT_FORMAT == 'latex':
        density, scale = 300, 150
        scale = scale * options.get('scale', 100) / 100
        filename = '%s-tree-%s.pdf' % (OUTPUT_BASENAME, _treenum)
        align = LATEX_VALIGN_IS_BROKEN and 'bottom' or 'top'
    elif OUTPUT_FORMAT == 'html':
        density, scale = 100, 100
        density = density * options.get('scale', 100) / 100
        filename = '%s-tree-%s.png' % (OUTPUT_BASENAME, _treenum)
        align = 'top'
    elif OUTPUT_FORMAT == 'ref':
        return []
    else:
        assert 0, 'bad output format %r' % OUTPUT_FORMAT
    try:
        filename = os.path.join(TREE_IMAGE_DIR, filename)
        tree_to_image(text, filename, density)
    except Exception, e:
        print 'Error parsing tree: %s\n%s' % (e, text)
        return [example(text, text)]

    imagenode = docutils.nodes.image(uri=filename, scale=scale, align=align)
    return [imagenode]

tree_directive.arguments = (1,0,1)
tree_directive.content = True
tree_directive.options = {'scale': directives.nonnegative_int}
directives.register_directive('tree', tree_directive)

def avm_directive(name, arguments, options, content, lineno,
                      content_offset, block_text, state, state_machine):
    text = '\n'.join(content)
    node = example(text)
    state.nested_parse(content, content_offset, node)
    return [node]
avm_directive.content = True
directives.register_directive('avm', avm_directive)


def def_directive(name, arguments, options, content, lineno,
                  content_offset, block_text, state, state_machine):
    state_machine.document.setdefault('__defs__', {})[arguments[0]] = 1
    return []
def_directive.arguments = (1, 0, 0)
directives.register_directive('def', def_directive)
    
def ifdef_directive(name, arguments, options, content, lineno,
                    content_offset, block_text, state, state_machine):
    if arguments[0] in state_machine.document.get('__defs__', ()):
        node = docutils.nodes.compound('')
        state.nested_parse(content, content_offset, node)
        return [node]
    else:
        return []
ifdef_directive.arguments = (1, 0, 0)
ifdef_directive.content = True
directives.register_directive('ifdef', ifdef_directive)
    
def ifndef_directive(name, arguments, options, content, lineno,
                    content_offset, block_text, state, state_machine):
    if arguments[0] not in state_machine.document.get('__defs__', ()):
        node = docutils.nodes.compound('')
        state.nested_parse(content, content_offset, node)
        return [node]
    else:
        return []
ifndef_directive.arguments = (1, 0, 0)
ifndef_directive.content = True
directives.register_directive('ifndef', ifndef_directive)
    
######################################################################
#{ Bibliography
######################################################################

class Citations(Transform):
    default_priority = 500 # before footnotes.
    def apply(self):
        bibliography = self.read_bibinfo(BIBTEX_FILE)
        for k, citation_refs in self.document.citation_refs.items():
            for citation_ref in citation_refs[:]:
                cite = bibliography.get(citation_ref['refname'].lower())
                if cite:
                    new_cite = self.citeref(cite, citation_ref['refname'])
                    citation_ref.replace_self(new_cite)
                    self.document.citation_refs[k].remove(citation_ref)

    def citeref(self, cite, key):
        if LOCAL_BIBLIOGRAPHY:
            return docutils.nodes.raw('', '\cite{%s}' % key, format='latex')
        else:
            return docutils.nodes.reference('', '', docutils.nodes.Text(cite),
                                    refuri='%s#%s' % (BIBLIOGRAPHY_HTML, key))

    BIB_ENTRY = re.compile(r'@\w+{.*')
    def read_bibinfo(self, filename):
        bibliography = {} # key -> authors, year
        key = None
        for line in open(filename):
            line = line.strip()
            
            # @InProceedings{<key>,
            m = re.match(r'@\w+{([^,]+),$', line)
            if m:
                key = m.group(1).strip().lower()
                bibliography[key] = [None, None]
                
            #   author = <authors>,
            m = re.match(r'(?i)author\s*=\s*(.*)$', line)
            if m and key:
                bibliography[key][0] = self.bib_authors(m.group(1))
                
            #   year = <year>,
            m = re.match(r'(?i)year\s*=\s*(.*)$', line)
            if m and key:
                bibliography[key][1] = self.bib_year(m.group(1))
        for key in bibliography:
            if bibliography[key][0] is None: print 'no author found:', key
            if bibliography[key][1] is None: print 'no year found:', key
            bibliography[key] = '[%s, %s]' % tuple(bibliography[key])
            #print '%20s %s' % (key, `bibliography[key]`)
        return bibliography

    def bib_year(self, year):
        return re.sub(r'["\'{},]', "", year)

    def bib_authors(self, authors):
        # Strip trailing comma:
        if authors[-1:] == ',': authors=authors[:-1]
        # Strip quotes or braces:
        authors = re.sub(r'"(.*)"$', r'\1', authors)
        authors = re.sub(r'{(.*)}$', r'\1', authors)
        authors = re.sub(r"'(.*)'$", r'\1', authors)
        # Split on 'and':
        authors = re.split(r'\s+and\s+', authors)
        # Keep last name only:
        authors = [a.split()[-1] for a in authors]
        # Combine:
        if len(authors) == 1:
            return authors[0]
        elif len(authors) == 2:
            return '%s & %s' % tuple(authors)
        elif len(authors) == 3:
            return '%s, %s, & %s' % tuple(authors)
        else:
            return '%s et al' % authors[0]
        return authors

        
        

######################################################################
#{ Indexing
######################################################################

#class termdef(docutils.nodes.Inline, docutils.nodes.TextElement): pass
class idxterm(docutils.nodes.Inline, docutils.nodes.TextElement): pass
class index(docutils.nodes.Element): pass

def idxterm_role(name, rawtext, text, lineno, inliner,
                 options={}, content=[]):
    if name == 'dt': options['classes'] = ['termdef']
    elif name == 'topic': options['classes'] = ['topic']
    else: options['classes'] = ['term']
    return [idxterm(rawtext, docutils.utils.unescape(text), **options)], []

roles.register_canonical_role('dt', idxterm_role)
roles.register_canonical_role('idx', idxterm_role)
roles.register_canonical_role('topic', idxterm_role)

def index_directive(name, arguments, options, content, lineno,
                    content_offset, block_text, state, state_machine):
    pending = docutils.nodes.pending(ConstructIndex)
    pending.details.update(options)
    state_machine.document.note_pending(pending)
    return [index('', pending)]
index_directive.arguments = (0, 0, 0)
index_directive.content = False
directives.register_directive('index', index_directive)

class SaveIndexTerms(Transform):
    default_priority = 810 # before NumberReferences transform
    def apply(self):
        v = FindTermVisitor(self.document)
        self.document.walkabout(v)
        
        if OUTPUT_FORMAT == 'ref':
            d = shelve.open('%s.ref' % OUTPUT_BASENAME)
            d['terms'] = v.terms
            d.close()

class ConstructIndex(Transform):
    default_priority = 820 # after NumberNodes, before NumberReferences.
    def apply(self):
        # Find any indexed terms in this document.
        v = FindTermVisitor(self.document)
        self.document.walkabout(v)
        terms = v.terms

        # Check the extern reference files for additional terms.
        for filename in EXTERN_REFERENCE_FILES:
            basename = os.path.splitext(filename)[0]
            d = shelve.open('%s.ref' % basename, 'r')
            terms.update(d['terms'])
            d.close()

        # Build the index & insert it into the document.
        index_node = self.build_index(terms)
        self.startnode.replace_self(index_node)

    def build_index(self, terms):
        if not terms: return []
        
        top = docutils.nodes.bullet_list('', classes=['index'])
        start_letter = None
        
        section = None
        for key in sorted(terms.keys()):
            if key[:1] != start_letter:
                top.append(docutils.nodes.list_item(
                    '', docutils.nodes.paragraph('', key[:1].upper()+'\n',
                                                 classes=['index-heading']),
                    docutils.nodes.bullet_list('', classes=['index-section']),
                    classes=['index']))
                section = top[-1][-1]
            section.append(self.entry(terms[key]))
            start_letter = key[:1]
        
        return top

    def entry(self, term_info):
        entrytext, name, sectnum = term_info
        if sectnum is not None:
            entrytext.append(docutils.nodes.emphasis('', ' (%s)' % sectnum))
        ref = docutils.nodes.reference('', '', refid=name,
                                       #resolved=True,
                                       *entrytext)
        para = docutils.nodes.paragraph('', '', ref)
        return docutils.nodes.list_item('', para, classes=['index'])

class FindTermVisitor(docutils.nodes.SparseNodeVisitor):
    def __init__(self, document):
        self.terms = {}
        docutils.nodes.NodeVisitor.__init__(self, document)
    def unknown_visit(self, node): pass
    def unknown_departure(self, node): pass

    def visit_idxterm(self, node):
        node['name'] = node['id'] = self.idxterm_key(node)
        node['names'] = node['ids'] = [node['id']]
        container = self.container_section(node)

        entrytext = node.deepcopy()
        sectnum = container.get('sectnum')
        name = node['name']
        self.terms[node['name']] = (entrytext, name, sectnum)
            
    def idxterm_key(self, node):
        key = re.sub('\W', '_', node.astext().lower())+'_index_term'
        if key not in self.terms: return key
        n = 2
        while '%s_%d' % (key, n) in self.terms: n += 1
        return '%s_%d' % (key, n)

    def container_section(self, node):
        while not isinstance(node, docutils.nodes.section):
            if node.parent is None: return None
            else: node = node.parent
        return node

######################################################################
#{ Crossreferences
######################################################################

class ResolveExternalCrossrefs(Transform):
    """
    Using the information from EXTERN_REFERENCE_FILES, look for any
    links to external targets, and set their `refuid` appropriately.
    Also, if they are a figure, section, table, or example, then
    replace the link of the text with the appropriate counter.
    """
    default_priority = 849 # right before dangling refs

    def apply(self):
        ref_dict = self.build_ref_dict()
        v = ExternalCrossrefVisitor(self.document, ref_dict)
        self.document.walkabout(v)

    def build_ref_dict(self):
        """{target -> (uri, label)}"""
        ref_dict = {}
        for filename in EXTERN_REFERENCE_FILES:
            basename = os.path.splitext(filename)[0]
            if OUTPUT_FORMAT == 'html':
                uri = os.path.split(basename)[-1]+'.html'
            else:
                uri = os.path.split(basename)[-1]+'.pdf'
            if not os.path.exists('%s.ref' % basename):
                print '%s.ref does not exist' % basename
            else:
                d = shelve.open('%s.ref' % basename, 'r')
                for ref in d['targets']:
                    label = d['reference_labels'].get(ref)
                    ref_dict[ref] = (uri, label)
                d.close()

        return ref_dict
    
class ExternalCrossrefVisitor(docutils.nodes.NodeVisitor):
    def __init__(self, document, ref_dict):
        docutils.nodes.NodeVisitor.__init__(self, document)
        self.ref_dict = ref_dict
    def unknown_visit(self, node): pass
    def unknown_departure(self, node): pass

    # Don't mess with the table of contents.
    def visit_topic(self, node):
        if 'contents' in node.get('classes', ()):
            raise docutils.nodes.SkipNode

    def visit_reference(self, node):
        if node.resolved: return
        node_id = node.get('refid') or node.get('refname')
        if node_id in self.ref_dict:
            uri, label = self.ref_dict[node_id]
            #print 'xref: %20s -> %-30s (label=%s)' % (
            #    node_id, uri+'#'+node_id, label)
            node['refuri'] = '%s#%s' % (uri, node_id)
            node.resolved = True

            if label is not None:
                node.children[:] = [docutils.nodes.Text(label)]
                expand_reference_text(node)

######################################################################
#{ Figure & Example Numbering
######################################################################

# [xx] number examples, figures, etc, relative to chapter?  e.g.,
# figure 3.2?  maybe number examples within-chapter, but then restart
# the counter?

class section_context(docutils.nodes.Invisible, docutils.nodes.Element):
    def __init__(self, context):
        docutils.nodes.Element.__init__(self, '', context=context)
        assert self['context'] in ('body', 'preface', 'appendix')

def section_context_directive(name, arguments, options, content, lineno,
                       content_offset, block_text, state, state_machine):
    return [section_context(name)]
section_context_directive.arguments = (0,0,0)
directives.register_directive('preface', section_context_directive)
directives.register_directive('body', section_context_directive)
directives.register_directive('appendix', section_context_directive)
        
class NumberNodes(Transform):
    """
    This transform adds numbers to figures, tables, and examples; and
    converts references to the figures, tables, and examples to use
    these numbers.  For example, given the rst source::

        .. _my_example:
        .. ex:: John likes Mary.

        See example my_example_.

    This transform will assign a number to the example, '(1)', and
    will replace the following text with 'see example (1)', with an
    appropriate link.
    """
    # dangling = 850; contents = 720.
    default_priority = 800
    def apply(self):
        v = NumberingVisitor(self.document)
        self.document.walkabout(v)
        self.document.reference_labels = v.reference_labels

class NumberReferences(Transform):
    default_priority = 830
    def apply(self):
        v = ReferenceVisitor(self.document, self.document.reference_labels)
        self.document.walkabout(v)

        # Save reference info to a pickle file.
        if OUTPUT_FORMAT == 'ref':
            d = shelve.open('%s.ref' % OUTPUT_BASENAME)
            d['reference_labels'] = self.document.reference_labels
            d['targets'] = v.targets
            d.close()

class NumberingVisitor(docutils.nodes.NodeVisitor):
    """
    A transforming visitor that adds figure numbers to all figures,
    and converts any references to figures to use the text 'Figure #';
    and adds example numbers to all examples, and converts any
    references to examples to use the text 'Example #'.
    """
    LETTERS = 'abcdefghijklmnopqrstuvwxyz'
    ROMAN = 'i ii iii iv v vi vii viii ix x'.split()
    ROMAN += ['x%s' % r for r in ROMAN]
    
    def __init__(self, document):
        docutils.nodes.NodeVisitor.__init__(self, document)
        self.reference_labels = {}
        self.figure_num = 0
        self.table_num = 0
        self.example_num = [0]
        self.section_num = [0]
        self.set_section_context = None
        self.section_context = 'body' # preface, appendix, body
        
    #////////////////////////////////////////////////////////////
    # Figures
    #////////////////////////////////////////////////////////////

    def visit_figure(self, node):
        self.figure_num += 1
        num = '%s.%s' % (self.format_section_num(1), self.figure_num)
        for node_id in self.get_ids(node):
            self.reference_labels[node_id] = '%s' % num
        self.label_node(node, 'Figure %s' % num)
            
    #////////////////////////////////////////////////////////////
    # Tables
    #////////////////////////////////////////////////////////////

    def visit_table(self, node):
        self.table_num += 1
        num = '%s.%s' % (self.format_section_num(1), self.table_num)
        for node_id in self.get_ids(node):
            self.reference_labels[node_id] = '%s' % num
        self.label_node(node, 'Table %s' % num)

    #////////////////////////////////////////////////////////////
    # Sections
    #////////////////////////////////////////////////////////////
    max_section_depth = 3
    no_section_numbers_in_preface = True
    TOP_SECTION = 'chapter'

    def visit_section(self, node):
        title = node[0]
        
        # Check if we're entering a new context.
        if len(self.section_num) == 1 and self.set_section_context:
            self.start_new_context(node)

        # Increment the section counter.
        self.section_num[-1] += 1
        
        # If a section number is given explicitly as part of the
        # title, then it overrides our counter.
        if isinstance(title.children[0], docutils.nodes.Text):
            m = re.match(r'(\d+(.\d+)*)\.?\s+', title.children[0].data)
            if m:
                pieces = [int(n) for n in m.group(1).split('.')]
                if len(pieces) == len(self.section_num):
                    self.section_num = pieces
                    title.children[0].data = title.children[0].data[m.end():]
                else:
                    print 'Error: section depth mismatch'
                self.prepend_raw_latex(node, r'\setcounter{%s}{%d}' %
                               (self.TOP_SECTION, self.section_num[0]-1))

        # Record the reference pointer for this section; and add the
        # section number to the section title.
        node['sectnum'] = self.format_section_num()
        for node_id in node.get('ids', []):
            self.reference_labels[node_id] = '%s' % node['sectnum']
        if (len(self.section_num) <= self.max_section_depth and
            (OUTPUT_FORMAT != 'latex') and
            not (self.section_context == 'preface' and
                 self.no_section_numbers_in_preface)):
            label = docutils.nodes.generated('', node['sectnum']+u'\u00a0'*3,
                                             classes=['sectnum'])
            title.insert(0, label)
            title['auto'] = 1
        
        self.section_num.append(0)

    def start_new_context(self,node):
        # Set the 'section_context' var.
        self.section_context = self.set_section_context
        self.set_section_context = None

        # Update our counter.
        self.section_num[0] = 0

        # Update latex's counter.
        if self.section_context == 'preface': style = 'Roman'
        elif self.section_context == 'body': style = 'arabic'
        elif self.section_context == 'appendix': style = 'Alph'
        raw_latex = (('\n'+r'\setcounter{%s}{0}' + '\n' + 
                      r'\renewcommand \the%s{\%s{%s}}'+'\n') %
               (self.TOP_SECTION, self.TOP_SECTION, style, self.TOP_SECTION))
        if self.section_context == 'appendix':
            raw_latex += '\\appendix\n'
        self.prepend_raw_latex(node, raw_latex)

    def prepend_raw_latex(self, node, raw_latex):
        node_index = node.parent.children.index(node)
        node.parent.insert(node_index, docutils.nodes.raw('', raw_latex,
                                                          format='latex'))
        
    def depart_section(self, node):
        self.section_num.pop()

    def format_section_num(self, depth=None):
        pieces = [str(p) for p in self.section_num]
        if self.section_context == 'body':
            pieces[0] = str(self.section_num[0])
        elif self.section_context == 'preface':
            pieces[0] = self.ROMAN[self.section_num[0]-1].upper()
        elif self.section_context == 'appendix':
            pieces[0] = self.LETTERS[self.section_num[0]-1].upper()
        else:
            assert 0, 'unexpected section context'
        if depth is None:
            return '.'.join(pieces)
        else:
            return '.'.join(pieces[:depth])
            
            
    def visit_section_context(self, node):
        assert node['context'] in ('body', 'preface', 'appendix')
        self.set_section_context = node['context']
        node.replace_self([])

    #////////////////////////////////////////////////////////////
    # Examples
    #////////////////////////////////////////////////////////////

    def visit_example(self, node):
        self.example_num[-1] += 1
        node['num'] = self.format_example_num()
        for node_id in self.get_ids(node):
            self.reference_labels[node_id] = '%s' % node['num']
        self.example_num.append(0)

    def depart_example(self, node):
        if self.example_num[-1] > 0:
            # If the example contains a list of subexamples, then
            # splice them in to our parent.
            node.replace_self(list(node))
        self.example_num.pop()

    def format_example_num(self):
        """ (1), (2); (1a), (1b); (1a.i), (1a.ii)"""
        ex_num = str(self.example_num[0])
        if len(self.example_num) > 1:
            ex_num += self.LETTERS[self.example_num[1]-1]
        if len(self.example_num) > 2:
            ex_num += '.%s' % self.ROMAN[self.example_num[2]-1]
        for n in self.example_num[3:]:
            ex_num += '.%s' % n
        return '(%s)' % ex_num

    #////////////////////////////////////////////////////////////
    # Helpers
    #////////////////////////////////////////////////////////////

    def unknown_visit(self, node): pass
    def unknown_departure(self, node): pass

    def get_ids(self, node):
        node_index = node.parent.children.index(node)
        if node_index>0 and isinstance(node.parent[node_index-1],
                                       docutils.nodes.target):
            target = node.parent[node_index-1]
            if target.has_key('refid'):
                refid = target['refid']
                target['ids'] = [refid]
                del target['refid']
                return [refid]
            elif target.has_key('ids'):
                return target['ids']
            else:
                print 'unable to find id for %s' % target
                return []
        return []

    def label_node(self, node, label):
        if isinstance(node[-1], docutils.nodes.caption):
            if OUTPUT_FORMAT == 'html':
                text = docutils.nodes.Text("%s: " % label)
                node[-1].children.insert(0, text)
        else:
            if OUTPUT_FORMAT == 'html':
                text = docutils.nodes.Text(label)
                node.append(docutils.nodes.caption('', '', text))
            else:
                node.append(docutils.nodes.caption()) # empty.
        
class ReferenceVisitor(docutils.nodes.NodeVisitor):
    def __init__(self, document, reference_labels):
        self.reference_labels = reference_labels
        self.targets = set()
        docutils.nodes.NodeVisitor.__init__(self, document)
    def unknown_visit(self, node):
        if isinstance(node, docutils.nodes.Element):
            self.targets.update(node.get('names', []))
            self.targets.update(node.get('ids', []))
    def unknown_departure(self, node): pass

    # Don't mess with the table of contents.
    def visit_topic(self, node):
        if 'contents' in node.get('classes', ()):
            raise docutils.nodes.SkipNode

    def visit_reference(self, node):
        node_id = node.get('refid') or node.get('refname')
        if node_id in self.reference_labels:
            label = self.reference_labels[node_id]
            node.children[:] = [docutils.nodes.Text(label)]
            expand_reference_text(node)

_EXPAND_REF_RE = re.compile(r'(?is)^(.*)(%s)\s+$' % '|'.join(
    ['figure', 'table', 'example', 'chapter', 'section', 'appendix',
     'sentence', 'tree']))
def expand_reference_text(node):
    """If the reference is immediately preceeded by the word 'figure'
    or the word 'table' or 'example', then include that word in the
    link (rather than just the number)."""
    node_index = node.parent.children.index(node)
    if node_index > 0:
        prev_node = node.parent.children[node_index-1]
        if (isinstance(prev_node, docutils.nodes.Text)):
            m = _EXPAND_REF_RE.match(prev_node.data)
            if m:
                prev_node.data = m.group(1)
                link = node.children[0]
                link.data = '%s %s' % (m.group(2), link.data)

######################################################################
#{ Doctest Indentation
######################################################################

class UnindentDoctests(Transform):
    """
    In our source text, we have indented most of the doctest blocks,
    for two reasons: it makes copy/pasting with the doctest script
    easier; and it's more readable.  But we don't *actually* want them
    to be included in block_quote environments when we output them.
    So this transform looks for any doctest_block's that are the only
    child of a block_quote, and eliminates the block_quote.
    """
    default_priority = 1000
    def apply(self):
        self.document.walkabout(UnindentDoctestVisitor(self.document))

class UnindentDoctestVisitor(docutils.nodes.NodeVisitor):
    def __init__(self, document):
        docutils.nodes.NodeVisitor.__init__(self, document)
    def unknown_visit(self, node): pass
    def unknown_departure(self, node): pass
    def visit_doctest_block(self, node):
        if (isinstance(node.parent, docutils.nodes.block_quote) and
            len(node.parent.children) == 1):
            node.parent.replace_self(node)
        
######################################################################
#{ HTML Output
######################################################################

class CustomizedHTMLWriter(HTMLWriter):
    settings_defaults = HTMLWriter.settings_defaults.copy()
    settings_defaults.update({
        'stylesheet': '../nltkdoc.css',
        'stylesheet_path': None,
        'output_encoding': 'ascii',
        'output_encoding_error_handler': 'xmlcharrefreplace',
        })
        
    def __init__(self):
        HTMLWriter.__init__(self)
        self.translator_class = CustomizedHTMLTranslator

    #def translate(self):
    #    postprocess(self.document)
    #    HTMLWriter.translate(self)

class CustomizedHTMLTranslator(HTMLTranslator):
    def visit_doctest_block(self, node):
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc)
        self.body.append(self.starttag(node, 'pre', CLASS='doctest-block'))
        self.body.append(pysrc)
        self.body.append('\n</pre>\n')
        raise docutils.nodes.SkipNode

    def depart_doctest_block(self, node):
        pass

    def visit_literal(self, node):
        """Process text to prevent tokens from wrapping."""
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc, True)
        self.body.append(
	    self.starttag(node, 'tt', '', CLASS='doctest'))
	self.body.append('<span class="pre">%s</span>' % pysrc)
        self.body.append('</tt>')
        # Content already processed:
        raise docutils.nodes.SkipNode
                          
    def _markup_pysrc(self, s, tag):
        return '\n'.join('<span class="pysrc-%s">%s</span>' %
                         (tag, self.encode(line))
                         for line in s.split('\n'))

    def visit_example(self, node):
        self.body.append(
            '<p><table border="0" cellpadding="0" cellspacing="0" '
            'class="example">\n  '
            '<tr valign="top"><td width="30" align="right">'
            '%s</td><td width="15"></td><td>' % node['num'])

    def depart_example(self, node):
        self.body.append('</td></tr></table></p>\n')

    def visit_idxterm(self, node):
        self.body.append('<a name="%s" />' % node['name'])
        self.body.append('<span class="%s">' % ' '.join(node['classes']))
        
    def depart_idxterm(self, node):
        self.body.append('</span>')

    def visit_index(self, node):
        self.body.append('<div class="index">\n<h1>Index</h1>\n')
        
    def depart_index(self, node):
        self.body.append('</div>\n')

######################################################################
#{ LaTeX Output
######################################################################

class CustomizedLaTeXWriter(LaTeXWriter):
    settings_defaults = LaTeXWriter.settings_defaults.copy()
    settings_defaults.update({
        'output_encoding': 'utf-8',
        'output_encoding_error_handler': 'backslashreplace',
        #'use_latex_docinfo': True,
        'font_encoding': 'C10,T1',
        'stylesheet': '../definitions.sty',
        'documentoptions': '11pt,twoside',
        'use_latex_footnotes': True,
        'use_latex_toc': True,
        })
    
    def __init__(self):
        LaTeXWriter.__init__(self)
        self.translator_class = CustomizedLaTeXTranslator

    #def translate(self):
    #    postprocess(self.document)
    #    LaTeXWriter.translate(self)
        
class CustomizedLaTeXTranslator(LaTeXTranslator):
    
    # Not sure why we need this, but the old Makefile did it so I will too:
    encoding = '\\usepackage[%s,utf8x]{inputenc}\n'

    linking = ('\\usepackage[colorlinks=%s,linkcolor=%s,urlcolor=%s,'
               'citecolor=blue,'
               'bookmarks=true,bookmarksopenlevel=2]{hyperref}\n')
    
    foot_prefix = [] # (used to add bibliography, when requested)

    def __init__(self, document):
        LaTeXTranslator.__init__(self, document)
        # This needs to go before the \usepackage{inputenc}:
        self.head_prefix.insert(1, '\\usepackage[cjkgb,postscript]{ucs}\n')
        # Make sure we put these *before* the stylesheet include line.
        self.head_prefix.insert(-2, textwrap.dedent("""\
            % Index:
            \\usepackage{makeidx}
            \\makeindex
            % For Python source code:
            \\usepackage{alltt}
            % Python source code: Prompt
            \\newcommand{\\pysrcprompt}[1]{\\textbf{#1}}
            \\newcommand{\\pysrcmore}[1]{\\textbf{#1}}
            % Python source code: Source code
            \\newcommand{\\pysrckeyword}[1]{\\textbf{#1}}
            \\newcommand{\\pysrcbuiltin}[1]{\\textbf{#1}}
            \\newcommand{\\pysrcstring}[1]{\\textit{#1}}
            \\newcommand{\\pysrcother}[1]{\\textbf{#1}}
            % Python source code: Comments
            \\newcommand{\\pysrccomment}[1]{\\textrm{#1}}
	    % Python interpreter: Traceback message
            \\newcommand{\\pysrcexcept}[1]{\\textbf{#1}}
            % Python interpreter: Output
            \\newcommand{\\pysrcoutput}[1]{#1}\n"""))

    def bookmark(self, node):
        # this seems broken; just use the hyperref package's
        # "bookmarks" option instead.
        return 

    def visit_doctest_block(self, node):
        self.literal = True
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc)
        self.literal = False
        self.body.append('\\begin{alltt}\n')
        self.body.append(pysrc)
        self.body.append('\\end{alltt}\n')
        raise docutils.nodes.SkipNode

    def depart_document(self, node):
        self.body += self.foot_prefix
        LaTeXTranslator.depart_document(self, node)

    def depart_doctest_block(self, node):
        pass

    def visit_literal(self, node):
        self.literal = True
        if self.node_is_inside_title(node):
            # Perhaps this should just add \texttt{node[0]}?
            markup_func = self._markup_pysrc
        else:
            markup_func = self._markup_pysrc_wrap
        pysrc = colorize_doctestblock(str(node[0]), markup_func, True)
        self.literal = False
        self.body.append('\\texttt{%s}' % pysrc)
        raise docutils.nodes.SkipNode

    def depart_literal(self, node):
	pass

    def node_is_inside_title(self, node):
        while node.parent is not None:
            if isinstance(node.parent, docutils.nodes.Titular):
                return True
            node = node.parent
        return False

    def visit_literal_block(self, node):
        if (self.settings.use_verbatim_when_possible and (len(node) == 1)
              # in case of a parsed-literal containing just a "**bold**" word:
              and isinstance(node[0], nodes.Text)):
            self.verbatim = 1
            self.body.append('\\begin{quote}\\begin{verbatim}\n')
        else:
            self.literal_block = 1
            self.insert_none_breaking_blanks = 1
            if self.active_table.is_open():
                self.body.append('\n{\\ttfamily \\raggedright '
                                 '\\noindent \\small\n')
            else:
                self.body.append('\\begin{quote}')
                self.body.append('{\\ttfamily \\raggedright '
                                 '\\noindent \\small\n')

    def _markup_pysrc(self, s, tag):
        return '\n'.join('\\pysrc%s{%s}' % (tag, line)
                         for line in self.encode(s).split('\n'))

    def _markup_pysrc_wrap(self, s, tag):
        """This version adds latex commands to allow for line wrapping
        within literals."""
        if '\255' in s:
            print 'Warning: literal contains char \\255'
            return self._markup_pysrc(s, tag)
        s = re.sub(r'(\W|\w\b)(?=.)', '\\1\255', s)
        s = self.encode(s).replace('\255', '{\linebreak[0]}')
        return '\n'.join('\\pysrc%s{%s}' % (tag, line)
                         for line in s.split('\n'))

    def visit_image(self, node):
        """So image scaling manually"""
        # Images are rendered using \includegraphics from the graphicx
        # package.  By default, it assumes that bitmapped images
        # should be rendered at 72 DPI; but we'd rather use a
        # different scale.  So adjust the scale attribute & then
        # delegate to our parent class.
        node.attributes['scale'] = (node.attributes.get('scale', 100) *
                                    72.0/LATEX_DPI)
        return LaTeXTranslator.visit_image(self, node)
        
    def visit_example(self, node):
        self.body.append('\\begin{itemize}\n\item[%s] ' % node['num'])

    def depart_example(self, node):
        self.body.append('\\end{itemize}\n')

    def visit_idxterm(self, node):
        self.body.append('\\index{%s}' % node.astext())
        if 'topic' in node['classes']:
            raise docutils.nodes.SkipNode
        elif 'termdef' in node['classes']:
            self.body.append('\\textbf{')
        else:
            self.body.append('\\textit{')
        
    def depart_idxterm(self, node):
        self.body.append('}')
    
    def visit_index(self, node):
        self.body.append('\\printindex')
        raise docutils.nodes.SkipNode

    #def depart_title(self, node):
    #    LaTeXTranslator.depart_title(self, node)
    #    if self.section_level == 1:
    #        title = self.encode(node.children[0].astext())
    #        sectnum = node.parent.get('sectnum')
    #        if sectnum:
    #            self.body.append('\\def\\chtitle{%s. %s}\n' %
    #                             (sectnum, title))
    #        else:
    #            self.body.append('\\def\\chtitle{}\n')

    #def visit_reference(self, node):
    #    """The visit_reference method in LaTeXTranslator escapes the
    #    '#' in URLs; but this seems to be the wrong thing to do, at
    #    least when using pdflatex.  So override that behavior."""
    #    if node.has_key('refuri'):
    #        self.body.append('\\href{%s}{' % node['refuri'])
    #    else:
    #        LaTeXTranslator.visit_reference(self, node)

######################################################################
#{ Source Code Highlighting
######################################################################

# Regular expressions for colorize_doctestblock
# set of keywords as listed in the Python Language Reference 2.4.1
# added 'as' as well since IDLE already colorizes it as a keyword.
# The documentation states that 'None' will become a keyword
# eventually, but IDLE currently handles that as a builtin.
_KEYWORDS = """
and       del       for       is        raise    
assert    elif      from      lambda    return   
break     else      global    not       try      
class     except    if        or        while    
continue  exec      import    pass      yield    
def       finally   in        print
as
""".split()
_KEYWORD = '|'.join([r'\b%s\b' % _KW for _KW in _KEYWORDS])

_BUILTINS = [_BI for _BI in dir(__builtins__) if not _BI.startswith('__')]
_BUILTIN = '|'.join([r'\b%s\b' % _BI for _BI in _BUILTINS])

_STRING = '|'.join([r'("""("""|.*?((?!").)"""))', r'("("|.*?((?!").)"))',
                    r"('''('''|.*?[^\\']'''))", r"('('|.*?[^\\']'))"])
_COMMENT = '(#.*?$)'
_PROMPT1 = r'^\s*>>>(?:\s|$)'
_PROMPT2 = r'^\s*\.\.\.(?:\s|$)'

PROMPT_RE = re.compile('(%s|%s)' % (_PROMPT1, _PROMPT2),
		       re.MULTILINE | re.DOTALL)
PROMPT2_RE = re.compile('(%s)' % _PROMPT2, re.MULTILINE | re.DOTALL)
'''The regular expression used to find Python prompts (">>>" and
"...") in doctest blocks.'''

EXCEPT_RE = re.compile(r'(.*)(^Traceback \(most recent call last\):.*)',
                       re.DOTALL | re.MULTILINE)

DOCTEST_DIRECTIVE_RE = re.compile(r'#\s*doctest:.*')

DOCTEST_RE = re.compile(r"""(?P<STRING>%s)|(?P<COMMENT>%s)|"""
                        r"""(?P<KEYWORD>(%s))|(?P<BUILTIN>(%s))|"""
                        r"""(?P<PROMPT1>%s)|(?P<PROMPT2>%s)|"""
                        r"""(?P<OTHER_WHITESPACE>\s)|(?P<OTHER>.)""" %
  (_STRING, _COMMENT, _KEYWORD, _BUILTIN, _PROMPT1, _PROMPT2),
  re.MULTILINE | re.DOTALL)
'''The regular expression used by L{_doctest_sub} to colorize doctest
blocks.'''

def colorize_doctestblock(s, markup_func, inline=False, strip_directives=True):
    """
    Colorize the given doctest string C{s} using C{markup_func()}.
    C{markup_func()} should be a function that takes a substring and a
    tag, and returns a colorized version of the substring.  E.g.:

        >>> def html_markup_func(s, tag):
        ...     return '<span class="%s">%s</span>' % (tag, s)

    The tags that will be passed to the markup function are: 
        - C{prompt} -- the Python PS1 prompt (>>>)
	- C{more} -- the Python PS2 prompt (...)
        - C{keyword} -- a Python keyword (for, if, etc.)
        - C{builtin} -- a Python builtin name (abs, dir, etc.)
        - C{string} -- a string literal
        - C{comment} -- a comment
	- C{except} -- an exception traceback (up to the next >>>)
        - C{output} -- the output from a doctest block.
        - C{other} -- anything else (does *not* include output.)
    """
    pysrc = [] # the source code part of a docstest block (lines)
    pyout = [] # the output part of a doctest block (lines)
    result = []
    out = result.append

    if strip_directives:
        s = DOCTEST_DIRECTIVE_RE.sub('', s)

    # Use this var to aggregate 'other' regions, since the regexp just
    # gives it to us one character at a time:
    other = [] 
    
    def subfunc(match):
        if match.group('OTHER'):
            other.extend(match.group())
            return ''
        elif other:
            v = markup_func(''.join(other), 'other')
            del other[:]
        else:
            v = ''

        if match.group('OTHER_WHITESPACE'):
            return v+match.group() # No coloring for other-whitespace.
        if match.group('PROMPT1'):
            return v+markup_func(match.group(), 'prompt')
	if match.group('PROMPT2'):
	    return v+markup_func(match.group(), 'more')
        if match.group('KEYWORD'):
            return v+markup_func(match.group(), 'keyword')
        if match.group('BUILTIN'):
            return v+markup_func(match.group(), 'builtin')
        if match.group('COMMENT'):
            return v+markup_func(match.group(), 'comment')
        if match.group('STRING') and '\n' not in match.group():
            return v+markup_func(match.group(), 'string')
        elif match.group('STRING'):
            # It's a multiline string; colorize the string & prompt
            # portion of each line.
            pieces = [markup_func(s, ['string','more'][i%2])
                      for i, s in enumerate(PROMPT2_RE.split(match.group()))]
            return v+''.join(pieces)
        else:
            assert 0, 'unexpected match'

    if inline:
	pysrc = DOCTEST_RE.sub(subfunc, s)
        if other: pysrc += markup_func(''.join(other), 'other')
	return pysrc.strip()

    # need to add a third state here for correctly formatting exceptions

    for line in s.split('\n')+['\n']:
        if PROMPT_RE.match(line):
            pysrc.append(line)
            if pyout:
                pyout = '\n'.join(pyout).rstrip()
                m = EXCEPT_RE.match(pyout)
                if m:
                    pyout, pyexc = m.group(1).strip(), m.group(2).strip()
                    if pyout:
                        print ('Warning: doctest does not allow for mixed '
                               'output and exceptions!')
                        result.append(markup_func(pyout, 'output'))
                    result.append(markup_func(pyexc, 'except'))
                else:
                    result.append(markup_func(pyout, 'output'))
                pyout = []
        else:
            pyout.append(line)
            if pysrc:
                pysrc = DOCTEST_RE.sub(subfunc, '\n'.join(pysrc))
                if other: pysrc += markup_func(''.join(other), 'other')
                result.append(pysrc.strip())
                #result.append(markup_func(pysrc.strip(), 'python'))
                pysrc = []

    remainder = '\n'.join(pyout).rstrip()
    if remainder:
        result.append(markup_func(remainder, 'output'))
        
    return '\n'.join(result)

######################################################################
#{ Old Code
######################################################################
# This was added so that chapter numbers could be propagated 
# to subsections properly; this is now done as part of the generation
# of the section numbering, rather than as a post-processing step.

# # Add chapter numbers; docutils doesn't handle (multi-file) books
# def chapter_numbers(out_file):
#     f = open(out_file).read()
#     # LaTeX
#     c = re.search(r'pdftitle={(\d+)\. ([^}]+)}', f)
#     if c:
#         chnum = c.group(1)
#         chtitle = c.group(2)
#         f = re.sub(r'(pdfbookmark\[\d+\]{)', r'\g<1>'+chnum+'.', f)
#         f = re.sub(r'(section\*{)', r'\g<1>'+chnum+'.', f)
#         f = re.sub(r'(\\begin{document})',
#                    r'\def\chnum{'+chnum+r'}\n' +
#                    r'\def\chtitle{'+chtitle+r'}\n' +
#                    r'\g<1>', f)
#         open(out_file, 'w').write(f)
#     # HTML
#     c = re.search(r'<h1 class="title">(\d+)\.', f)
#     if c:
#         chapter = c.group(1)
#         f = re.sub(r'(<h\d><a[^>]*>)', r'\g<1>'+chapter+'.', f)
#         open(out_file, 'w').write(f)

######################################################################
#{ Customized Reader (register new transforms)
######################################################################

class CustomizedReader(StandaloneReader):
    _TRANSFORMS = [
        Citations,                  #  500
        NumberNodes,                #  800
        SaveIndexTerms,             #  810
        NumberReferences,           #  830
        ResolveExternalCrossrefs,   #  849
        UnindentDoctests,           # 1000
        ]
    def get_transforms(self):
        return StandaloneReader.get_transforms(self) + self._TRANSFORMS

######################################################################
#{ Logging
######################################################################

try:
    from epydoc.cli import ConsoleLogger
    logger = ConsoleLogger(0)
    #def log(msg): logger.progress(0, msg)
except Exception, e:
    class FakeLogger:
        def __getattr__(self, a):
            return (lambda *args: None)
    logger = FakeLogger()

# monkey-patch RSTState to give us progress info.
from docutils.parsers.rst.states import RSTState
_old_RSTState_section = RSTState.section
_section = 'Parsing'
def _new_RSTState_section(self, title, source, style, lineno, messages):
    lineno = self.state_machine.abs_line_number()
    numlines = (len(self.state_machine.input_lines) +
                self.state_machine.input_offset)
    progress = 0.5 * lineno / numlines
    global _section
    if style == ('=','='): _section = title
    logger.progress(progress, '%s -- line %d/%d' % (_section,lineno,numlines))
    _old_RSTState_section(self, title, source, style, lineno, messages)
RSTState.section = _new_RSTState_section

# monkey-patch Publisher to give us progress info.
from docutils.core import Publisher
_old_Publisher_apply_transforms = Publisher.apply_transforms
def _new_Publisher_apply_transforms(self):
    logger.progress(.6, 'Processing Document Tree')
    _old_Publisher_apply_transforms(self)
    logger.progress(.9, 'Writing Output')
Publisher.apply_transforms = _new_Publisher_apply_transforms

######################################################################
#{ Main Script
######################################################################
__version__ = 0.2

def parse_args():
    optparser = OptionParser()

    optparser.add_option("--html", 
        action="store_const", dest="action", const="html",
        help="Write HTML output.")
    optparser.add_option("--latex", "--tex",
        action="store_const", dest="action", const="latex",
        help="Write LaTeX output.")
    optparser.add_option("--ref",
        action="store_const", dest="action", const="ref",
        help="Generate references linking file.")
    optparser.add_option("--documentclass",
        action="store", dest="documentclass", 
        help="Document class for latex output (article, book).")
    optparser.add_option("--a4",
        action="store_const", dest="papersize", const="a4paper",
        help="Use a4 paper size.")
    optparser.add_option("--letter",
        action="store_const", dest="papersize", const="letterpaper",
        help="Use letter paper size.")
    optparser.add_option("--bibliography",
        action="store_const", dest="bibliography", const=True,
        help="Include a bibliography (LaTeX only).")

    optparser.set_defaults(action='html', documentclass='report',
                           papersize='letterpaper', bibliography=False)

    options, filenames = optparser.parse_args()
    return options, filenames

def main():
    global OUTPUT_FORMAT, OUTPUT_BASENAME, EXTERN_REFERENCE_FILES
    options, filenames = parse_args()

    if not os.path.exists(TREE_IMAGE_DIR):
        os.mkdir(TREE_IMAGE_DIR)

    if docutils.writers.html4css1.Image is None:
        print ('WARNING: Cannot scale images in HTML unless Python '
               'Imaging\n         Library (PIL) is installed!')

    EXTERN_REFERENCE_FILES = [f for f in filenames if
                              f.endswith('.ref')]
    filenames = [f for f in filenames if not f.endswith('.ref')]

    CustomizedLaTeXWriter.settings_defaults.update(dict(
        documentclass = options.documentclass,
        use_latex_docinfo = (options.documentclass=='book')))
    CustomizedLaTeXWriter.settings_defaults['documentoptions'] += (
        ','+options.papersize)
    
    if options.documentclass == 'article':
        NumberingVisitor.TOP_SECTION = 'section'
    else:
        NumberingVisitor.TOP_SECTION = 'chapter'

    if options.bibliography:
        LOCAL_BIBLIOGRAPHY = True
        CustomizedLaTeXTranslator.foot_prefix += [
            '\\bibliographystyle{apalike}\n',
            '\\bibliography{%s}\n' % BIBTEX_FILE]
        
    OUTPUT_FORMAT = options.action
    if options.action == 'html':
        writer = CustomizedHTMLWriter()
        output_ext = '.html'
    elif options.action == 'latex':
        writer = CustomizedLaTeXWriter()
        output_ext = '.tex'
    elif options.action == 'ref':
        writer = None
        output_ext = '.ref'
    else:
        assert 0, 'bad action'

    for in_file in filenames:
        OUTPUT_BASENAME = os.path.splitext(in_file)[0]
        out_file = os.path.splitext(in_file)[0] + output_ext
        logger.start_progress()#'%s -> %s' % (in_file, out_file))
        if in_file == out_file: out_file += output_ext
        if writer is None:
            if os.path.exists(out_file): os.remove(out_file)
            docutils.core.publish_doctree(source=None, source_path=in_file,
                                          source_class=docutils.io.FileInput,
                                          reader=CustomizedReader())
        else:
            docutils.core.publish_file(source_path=in_file, writer=writer,
                                       destination_path=out_file,
                                       reader=CustomizedReader())
        logger.end_progress()

if __name__ == '__main__':
    main()
