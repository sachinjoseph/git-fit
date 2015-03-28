#!/usr/bin/env python2.7

from os.path import dirname, realpath, relpath, join as joinpath, sep as pathSeparator

class FitNode:
    def __init__(self, path, nodes):
        self.parentPath = path
        self.children = nodes

# Returns a tree constructed from given list of paths
def getPathTree(paths):
    tree = {}
    for p in paths:
        parts = p.split('/')
        node = tree.setdefault(parts[0], {})
        for c in parts[1:]:
            node = node.setdefault(c, {})
    return tree

def fitMapToTree(fitData):
    tree = {}
    for p,d in fitData.iteritems():
        parts = p.split('/')
        if len(parts) == 1:
            tree[p] = d
            continue
        node = tree.setdefault(parts[0], {})
        for c in parts[1:-1]:
            node = node.setdefault(c, {})
        node[parts[-1]] = d
    return tree

def fitTreeToMap(fitTree):
    fitData = {}
    for k,v in fitTree.iteritems():
        if type(v) == type({}):
            _fitMapToTreeRec(fitData, k, v.iteritems())
        else:
            fitData[k] = v
    return fitData

def _fitMapToTreeRec(fitData, path, items):
    for k,v in items:
        next_path = path+'/'+k
        if type(v) == type({}):
            _fitMapToTreeRec(fitData, next_path, v.iteritems())
        else:
            fitData[next_path] = v

def _addFitItemsToList(path, node, items):
    # keep a queue of nodes, adding all leafs to fitPaths
    nodes = [FitNode(path, node)]
    while len(nodes) > 0:
        node = nodes.pop(0)
        if len(node.children) == 0:
            #Replacement of '\\' is needed(Windows) since cache is already formed and it has paths in UNIX format
            items.add(node.parentPath.replace('\\', '/'))
        else:
            nodes.extend([FitNode(node.parentPath.replace('\\', '/') + '/' + k, v) for k,v in node.children.iteritems()])

def getValidFitPaths(given, available, basePath='', workingDir=''):
    if not given:
        return None

    # Normalize the user-entered paths into canonical paths relative to basePath
    given = {relpath(realpath(joinpath(workingDir,p)), basePath) for p in given}
    validPaths = set(available) if '.' in given else set()
    fitPathTree = getPathTree(available)

    # Generate list of individual fit items under user-given paths
    for p in given:
        if p.startswith('..' + pathSeparator):
            print '(...skipping path not under repo: %s)'%p
            continue

        # Determine if normalized user-given path is one that
        # is tracked by fit by traversing fitPathTree
        isFit = True
        node = fitPathTree
        parts = p.split(pathSeparator)
        for part in parts:
            node = node.get(part)
            if node == None:
                isFit = False
                break

        if not isFit:
            print '(...path not currently tracked by fit: %s)'%p
            continue

        _addFitItemsToList(p, node, validPaths)

    return validPaths
