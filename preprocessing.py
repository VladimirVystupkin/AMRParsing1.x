#!/usr/bin/python
import sys,argparse,re,os
from stanfordnlp.corenlp import *
from common.AMRGraph import *
from pprint import pprint
import cPickle as pickle
from Aligner import Aligner
from common.SpanGraph import SpanGraph
from depparser import CharniakParser,StanfordDepParser,ClearDepParser,TurboDepParser, MateDepParser
from collections import OrderedDict
import constants

log = sys.stdout

def load_hand_alignments(hand_aligned_file):
    hand_alignments = {}
    comments, amr_strings = readAMR(hand_aligned_file)
    for comment, amr_string in zip(comments,amr_strings):
        hand_alignments[comment['id']] = comment['alignments']
    return hand_alignments
        

def readAMR(amrfile_path):
    amrfile = codecs.open(amrfile_path,'r',encoding='utf-8')
    comment_list = []
    comment = OrderedDict()
    amr_list = []
    amr_string = ''

    for line in amrfile.readlines():
        if line.startswith('#'):
            for m in re.finditer("::([^:\s]+)\s(((?!::).)*)",line):
                #print m.group(1),m.group(2)
                comment[m.group(1)] = m.group(2)
        elif not line.strip():
            if amr_string and comment:
                comment_list.append(comment)
                amr_list.append(amr_string)
                amr_string = ''
                comment = {}
        else:
            amr_string += line.strip()+' '

    if amr_string and comment:
        comment_list.append(comment)
        amr_list.append(amr_string)
    amrfile.close()

    return (comment_list,amr_list)

def _write_sentences(file_path,sentences):
    """
    write out the sentences to file
    """
    output = codecs.open(file_path,'w',encoding='utf-8')
    for sent in sentences:
        output.write(sent+'\n')
    output.close()

def _write_tok_sentences(file_path,instances,comments=None):
    output_tok = open(file_path,'w')
    for i,inst in enumerate(instances):
        if comments:
            output_tok.write("%s %s\n" % (comments[i]['id'],' '.join(inst.get_tokenized_sent())))
        else:
            output_tok.write("%s\n" % (' '.join(inst.get_tokenized_sent())))
    output_tok.close()

def _write_tok_amr(file_path,amr_file,instances):
    output_tok = open(file_path,'w')
    origin_comment_string = ''
    origin_amr_string = ''
    comment_list = []
    amr_list = []
    for line in open(amr_file,'r').readlines():
        if line.startswith('#'):
            origin_comment_string += line 
        elif not line.strip():
            if origin_amr_string and origin_comment_string:
                comment_list.append(origin_comment_string)
                amr_list.append(origin_amr_string)

                origin_amr_string = ''
                origin_comment_string = ''
        else:
            origin_amr_string += line
    if origin_amr_string and origin_comment_string:
        comment_list.append(origin_comment_string)
        amr_list.append(origin_amr_string)

    for i in xrange(len(instances)):
        output_tok.write(comment_list[i])
        output_tok.write("# ::tok %s\n" % (' '.join(instances[i].get_tokenized_sent())))
        output_tok.write(amr_list[i])
        output_tok.write('\n')

    output_tok.close()

def _add_amr(instances,amr_strings):
    assert len(instances) == len(amr_strings)
    
    for i in range(len(instances)):
        instances[i].addAMR(AMR.parse_string(amr_strings[i]))

def _load_cparse(cparse_filename):
    '''
    load the constituent parse tree 
    '''
    from nltk.tree import Tree
    ctree_list = []
    with open(cparse_filename,'r') as cf:
        for line in cf:
            ctree_list.append(Tree(line.strip()))

    return ctree_list

def _fix_prop_head(inst,ctree,start_index,height):
    head_index = None
    tree_pos = ctree.leaf_treeposition(start_index)
    span_root = ctree[tree_pos[:-(height+1)]]
    end_index = start_index + len(span_root.leaves())
    cur = inst.tokens[start_index+1]
    visited = set()
    while cur['id'] - 1 < end_index and cur['id'] - 1 >= start_index:
        if cur['id'] not in visited:
            visited.add(cur['id'])
        else:
            cur = inst.tokens[cur['id']+1]
            continue
        head_index = cur['id'] - 1
        
        if 'head' in cur:
            cur = inst.tokens[cur['head']]
        else:
            cur = inst.tokens[cur['id']+1]

    return head_index
    
def _add_prop(instances,prop_filename,dep_filename,FIX_PROP_HEAD=False):
    ctree_list = None
    if FIX_PROP_HEAD:
        cparse_filename = dep_filename.rsplit('.',1)[0]
        ctree_list = _load_cparse(cparse_filename)
    with open(prop_filename,'r') as f:
        for line in f:
            prd_info = line.split('-----')[0]
            arg_info = line.split('-----')[1]
            fn,sid,ppos,ptype,pred,frameset = prd_info.strip().split()
            sid = int(sid)
            ppos = int(ppos)
            frameset = frameset.replace('.','-')
            for match in re.finditer('(\d+):(\d+)(\|(\d+))?\-([^:\|\s]+)',arg_info):
                start_index = int(match.group(1))
                height = int(match.group(2))
                head_index = match.group(4)
                label = match.group(5)
                if label != 'rel':
                    if FIX_PROP_HEAD: head_index = _fix_prop_head(instances[sid],ctree_list[sid],start_index,height)
                    instances[sid].addProp(ppos+1,frameset,int(head_index)+1,label)
                
            
def _add_dependency(instances,result,FORMAT="stanford"):
    if FORMAT=="stanford":
        i = 0
        for line in result.split('\n'):
            if line.strip():
                split_entry = re.split("\(|, ", line[:-1])
                
                if len(split_entry) == 3:
                    rel, l_lemma, r_lemma = split_entry
                    m = re.match(r'(?P<lemma>.+)-(?P<index>[^-]+)', l_lemma)
                    l_lemma, l_index = m.group('lemma'), m.group('index')
                    m = re.match(r'(?P<lemma>.+)-(?P<index>[^-]+)', r_lemma)
                    r_lemma, r_index = m.group('lemma'), m.group('index')
                    
                    instances[i].addDependency( rel, l_index, r_index )
                
            else:
                i += 1
    elif FORMAT == "clear":
        i = 0
        for line in result.split('\n'):
            if line.strip():
                line = line.split()
                instances[i].addDependency( line[6], line[5], line[0])
            else:
                i += 1
    elif FORMAT == "turbo":
        i = 0
        for line in result.split('\n'):
            if line.strip():
                line = line.split()
                instances[i].addDependency( line[7], line[6], line[0])
            else:
                i += 1
    elif FORMAT == "mate":
        i = 0
        for line in result.split('\n'):
            if line.strip():
                line = line.split()
                instances[i].addDependency( line[11], line[9], line[0])
            else:
                i += 1
    elif FORMAT in ["stanfordConvert","stdconv+charniak"]:
        i = 0
        for line in result.split('\n'):
            if line.strip():
                split_entry = re.split("\(|, ", line[:-1])
                
                if len(split_entry) == 3:
                    rel, l_lemma, r_lemma = split_entry
                    m = re.match(r'(?P<lemma>.+)-(?P<index>[^-]+)', l_lemma)
                    l_lemma, l_index = m.group('lemma'), m.group('index')
                    # some string may start with @; change the segmenter
                    m = re.match(r'(?P<lemma>[^\^]+)(\^(?P<trace>[^-]+))?-(?P<index>[^-]+)', r_lemma)
                    try:
                        r_lemma,r_trace, r_index = m.group('lemma'), m.group('trace'), m.group('index')
                    except AttributeError:
                        import pdb
                        pdb.set_trace()

                    if r_index != 'null':
                        #print >> sys.stderr, line                        
                        instances[i].addDependency( rel, l_index, r_index )
                    if r_trace is not None:
                        instances[i].addTrace( rel, l_index, r_trace )                      
                
            else:
                i += 1
    else:
        raise ValueError("Unknown dependency format!")

def preprocess(input_file,START_SNLP=True,INPUT_AMR=True):
    '''nasty function'''
    tmp_sent_filename = None
    instances = None
    tok_sent_filename = None
    
    if INPUT_AMR: # the input file is amr annotation
        
        amr_file = input_file
        aligned_amr_file = amr_file + '.amr.tok.aligned'
        if os.path.exists(aligned_amr_file):
            print >> log, "Using aligned amr file..."
            comments,amr_strings = readAMR(aligned_amr_file)
        else:
            comments,amr_strings = readAMR(amr_file)
        sentences = [c['snt'] for c in comments] # here should be 'snt'
        tmp_sent_filename = amr_file+'.sent'
        if not os.path.exists(tmp_sent_filename): # write sentences into file
            _write_sentences(tmp_sent_filename,sentences)


        print >> log, "Start Stanford CoreNLP..."
        proc1 = StanfordCoreNLP()

        # preprocess 1: tokenization, POS tagging and name entity using Stanford CoreNLP
        if START_SNLP: proc1.setup()
        instances = proc1.parse(tmp_sent_filename)

        tok_sent_filename = tmp_sent_filename+'.tok' # write tokenized sentence file
        if not os.path.exists(tok_sent_filename):
            _write_tok_sentences(tok_sent_filename,instances)

        tok_amr_filename = amr_file + '.amr.tok'
        if not os.path.exists(tok_amr_filename): # write tokenized amr file
            _write_tok_amr(tok_amr_filename,amr_file,instances)
            
        SpanGraph.graphID = 0
        for i in range(len(instances)):

            amr = AMR.parse_string(amr_strings[i])
            if 'alignments' in comments[i]:
                alignment,s2c_alignment = Aligner.readJAMRAlignment(amr,comments[i]['alignments'])
                #ggraph = SpanGraph.init_ref_graph(amr,alignment,instances[i].tokens)
                ggraph = SpanGraph.init_ref_graph_abt(amr,alignment,s2c_alignment,instances[i].tokens)
                #ggraph.pre_merge_netag(instances[i])
                #print >> log, "Graph ID:%s\n%s\n"%(ggraph.graphID,ggraph.print_tuples())
                instances[i].addComment(comments[i])
                instances[i].addAMR(amr)
                instances[i].addGoldGraph(ggraph)

    else:
        # input file is sentence
        tmp_sent_filename = input_file 

        print >> log, "Start Stanford CoreNLP ..."
        proc1 = StanfordCoreNLP()

        # preprocess 1: tokenization, POS tagging and name entity using Stanford CoreNLP
        if START_SNLP: proc1.setup()
        instances = proc1.parse(tmp_sent_filename)

        tok_sent_filename = tmp_sent_filename+'.tok' # write tokenized sentence file
        if not os.path.exists(tok_sent_filename):
            _write_tok_sentences(tok_sent_filename,instances)
        
    # preprocess 2: dependency parsing 
    if constants.FLAG_DEPPARSER == "stanford":
        dep_filename = tok_sent_filename+'.stanford.dep'
        if os.path.exists(dep_filename):
            print 'Read dependency file %s...' % (dep_filename)                                                                 
            dep_result = open(dep_filename,'r').read()
        else:
            dparser = StanfordDepParser()
            dep_result = dparser.parse(tok_sent_filename)
            output_dep = open(dep_filename,'w')            
            output_dep.write(dep_result)
            output_dep.close()
            
        _add_dependency(instances,dep_result)
    elif constants.FLAG_DEPPARSER == "stanfordConvert":
        dep_filename = tok_sent_filename+'.stanford.parse.dep'
        if os.path.exists(dep_filename):
            print 'Read dependency file %s...' % (dep_filename)

            dep_result = open(dep_filename,'r').read()
        else:
            raise IOError('Converted dependency file %s not founded' % (dep_filename))

        _add_dependency(instances,dep_result,constants.FLAG_DEPPARSER)

    elif constants.FLAG_DEPPARSER == "stdconv+charniak":
        dep_filename = tok_sent_filename+'.charniak.parse.dep'
        if not os.path.exists(dep_filename):
            dparser = CharniakParser()
            dparser.parse(tok_sent_filename)
            #raise IOError('Converted dependency file %s not founded' % (dep_filename))
        print 'Read dependency file %s...' % (dep_filename)
        dep_result = open(dep_filename,'r').read()
        _add_dependency(instances,dep_result,constants.FLAG_DEPPARSER)
            
    elif constants.FLAG_DEPPARSER == "clear":
        dep_filename = tok_sent_filename+'.clear.dep'
        if os.path.exists(dep_filename):
            print 'Read dependency file %s...' % (dep_filename)                                                                 
            dep_result = open(dep_filename,'r').read()
        else:
            dparser = ClearDepParser()
            dep_result = dparser.parse(tok_sent_filename)
        _add_dependency(instances,dep_result,constants.FLAG_DEPPARSER)

    elif constants.FLAG_DEPPARSER == "turbo":
        dep_filename = tok_sent_filename+'.turbo.dep'
        if os.path.exists(dep_filename):
            print 'Read dependency file %s...' % (dep_filename)                                                                 
            dep_result = open(dep_filename,'r').read()
        else:
            dparser = TurboDepParser()
            dep_result = dparser.parse(tok_sent_filename)
        _add_dependency(instances,dep_result,constants.FLAG_DEPPARSER)

    elif constants.FLAG_DEPPARSER == "mate":
        dep_filename = tok_sent_filename+'.mate.dep'
        if os.path.exists(dep_filename):
            print 'Read dependency file %s...' % (dep_filename)                                                                 
            dep_result = open(dep_filename,'r').read()
        else:
            dparser = MateDepParser()
            dep_result = dparser.parse(tok_sent_filename)
        _add_dependency(instances,dep_result,constants.FLAG_DEPPARSER)
    else:
        pass
    
    if constants.FLAG_PROP:
        print >> log, "Adding SRL information..."
        prop_filename = tok_sent_filename + '.prop'
        if os.path.exists(prop_filename):
            if constants.FLAG_DEPPARSER == "stdconv+charniak":
                _add_prop(instances,prop_filename,dep_filename,FIX_PROP_HEAD=True)
            else:
                _add_prop(instances,prop_filename,dep_filename)
            
        else:
            raise FileNotFoundError('Semantic role labeling file %s not found!'%(prop_filename))

        
    return instances
'''
def _init_instances(sent_file,amr_strings,comments):
    print >> log, "Preprocess 1:pos, ner and dependency using stanford parser..."
    proc = StanfordCoreNLP()
    instances = proc.parse(sent_file)
    
    
    print >> log, "Preprocess 2:adding amr and generating gold graph"
    assert len(instances) == len(amr_strings)
    for i in range(len(instances)):
        amr = AMR.parse_string(amr_strings[i])
        instances[i].addAMR(amr)
        alignment = Aligner.readJAMRAlignment(amr,comments[i]['alignments'])
        ggraph = SpanGraph.init_ref_graph(amr,alignment,comments[i]['snt'])
        ggraph.pre_merge_netag(instances[i])
        instances[i].addGoldGraph(ggraph)

    return instances


def add_JAMR_align(instances,aligned_amr_file):
    comments,amr_strings = readAMR(aligned_amr_file)
    for i in range(len(instances)):
        amr = AMR.parse_string(amr_strings[i])
        alignment = Aligner.readJAMRAlignment(amr,comments[i]['alignments'])
        ggraph = SpanGraph.init_ref_graph(amr,alignment,instances[i].tokens)
        ggraph.pre_merge_netag(instances[i])
        #print >> log, "Graph ID:%s\n%s\n"%(ggraph.graphID,ggraph.print_tuples())
        instances[i].addAMR(amr)
        instances[i].addGoldGraph(ggraph)

    #output_file = aligned_amr_file.rsplit('.',1)[0]+'_dataInst.p'
    #pickle.dump(instances,open(output_file,'wb'),pickle.HIGHEST_PROTOCOL)

def preprocess_aligned(aligned_amr_file,writeToFile=True):
    comments,amr_strings = readAMR(aligned_amr_file)
    sentences = [c['tok'] for c in comments]
    tmp_sentence_file = aligned_amr_file.rsplit('.',1)[0]+'_sent.txt'
    _write_sentences(tmp_sentence_file,sentences)
    
    instances = _init_instances(tmp_sentence_file,amr_strings,comments)
    if writeToFile:
        output_file = aligned_amr_file.rsplit('.',1)[0]+'_dataInst.p'
        pickle.dump(instances,open(output_file,'wb'),pickle.HIGHEST_PROTOCOL)
        
    return instances
'''

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="preprocessing for training/testing data")
    arg_parser.add_argument('-v','--verbose',action='store_true',default=False)
    #arg_parser.add_argument('-m','--mode',choices=['train','parse'])
    arg_parser.add_argument('-w','--writeToFile',action='store_true',help='write preprocessed sentences to file')
    arg_parser.add_argument('amr_file',help='amr bank file')
    
    args = arg_parser.parse_args()    

    instances = preprocess(args.amr_file)
    pprint(instances[1].toJSON())
    
