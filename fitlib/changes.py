
from . import fitFile, gitDirOperation, repoDir, savesDir, workingDir
from . import updateStats, refreshStats, addedStatFile, writeFitFile, readFitFile
from . import filterBinaryFiles, getStagedFitFileHash, getFitFileStatus
from objects import getUpstreamItems, getDownstreamItems
from paths import getValidFitPaths
import merge, cache
from subprocess import Popen as popen, PIPE
from os.path import exists, dirname, join as joinpath
from os import remove, makedirs, stat, listdir, mkdir
from shutil import copyfile
import re
from sys import stdout

restoreMissingMessage = '''
git-fit: %d objects were only lazily restored as empty stubs.
         Run 'git-fit get -s' for more information.
'''

def printLegend():
    print '==========================================================================='
    print 'Basic status symbols:'
    print '-----------------------------------'
    print '*   modified'
    print '+   added (fit will start tracking upon commit)'
    print '-   removed (physically deleted, fit will no longer track upon commit)'
    print '~   untracked (excluded from fit in gitattributes, fit will no longer track upon commit)'
    print
    print
    print 'Commit-aborting staged items in git'
    print '-----------------------------------'
    print 'F  an item fit is already tracking, but is also currently staged for commit in git'
    print 'B  a binary file staged for commit in git that fit has not been told to ignore'
    print
    print
    print 'Conflicted items during a merge'
    print '-----------------------------------'
    print '[*+-~]M   selected to be resolved with "mine"'
    print '[*+-~]T   selected to be resolved with "theirs"'
    print '[*+-~]W   selected to be resolved with working-tree'
    print '      U   no resolution yet selected'
    print 
    print 'For conflicting items with M, T, or W, the status indicated by the first-column'
    print 'symbol is relative to the version of the item selected for conflict resolution.'
    print '==========================================================================='
    print '\n'


def printStatus(fitTrackedData, pathArgs=None, legend=True, showall=False, mergeInfo=None):
    if legend:
        printLegend()

    trackedItems = getTrackedItems()
    fitItems = set(fitTrackedData)
    allItems = fitItems | trackedItems
    paths = None if not pathArgs else getValidFitPaths(pathArgs, allItems, basePath=repoDir, workingDir=workingDir)

    modifiedItems, addedItems, removedItems, untrackedItems, unchangedItems, stats, stubs = getChangedItems(fitTrackedData, trackedItems=trackedItems, paths=paths)

    conflict, binary = getStagedOffenders()
    offenders = conflict | binary

    modifiedItems = set(modifiedItems) - offenders
    addedItems = addedItems - offenders
    removedItems = removedItems - offenders
    untrackedItems = untrackedItems - offenders
    unchangedItems = unchangedItems - offenders

    downstream, skippedFiles = getDownstreamItems(fitTrackedData, fitItems if paths == None else paths, stats)
    upstream = getUpstreamItems()

    modified,added,removed,untracked,unchanged = [],[],[],[],[]

    if mergeInfo:
        mine, theirs, working, unresolved = mergeInfo
        mergeInfo = {i:'M' for i in mine}
        mergeInfo.update((i, 'T') for i in theirs)
        mergeInfo.update((i, 'W') for i in working)
        mergeInfo.update((i, 'U') for i in unresolved)
        mergeItems = set(mergeInfo)

        modified =  [('*%s '%mergeInfo[i], i) for i in modifiedItems & mergeItems]
        added =     [('+%s '%mergeInfo[i], i) for i in addedItems & mergeItems]
        removed =   [('-%s '%mergeInfo[i], i) for i in removedItems & mergeItems]
        untracked = [('~%s '%mergeInfo[i], i) for i in untrackedItems & mergeItems]
        unchanged = [(' %s '%mergeInfo[i], i) for i in unchangedItems & mergeItems]

        modifiedItems -= mergeItems
        addedItems -= mergeItems
        removedItems -= mergeItems
        untrackedItems -= mergeItems
        unchangedItems -= mergeItems

    unchangedItems = unchangedItems if showall else []

    modified.extend( ('*  ', i) for i in modifiedItems)
    added.extend(    ('+  ', i) for i in addedItems)
    removed.extend(  ('-  ', i) for i in removedItems)
    untracked.extend(('~  ', i) for i in untrackedItems)
    unchanged.extend(('   ', i) for i in unchangedItems)
    conflict =      [('F  ', i) for i in conflict]
    binary =        [('B  ', i) for i in binary]

    fitFileStatus = getFitFileStatus()
    dirtyFit = fitFileStatus and fitFileStatus[1] != ' '

    noChanges = all(len(l) == 0 for l in [modified,added,removed,untracked,unchanged,conflict,binary,upstream,downstream,stubs])

    if noChanges and not dirtyFit:
        print 'Nothing to show (no problems or changes detected).'
        return

    if any(len(l) > 0 for l in [modified,added,removed,untracked,unchanged,conflict,binary]):
        print
        for c,f in sorted(untracked+modified+added+removed+conflict+binary+unchanged, key=lambda i: i[1]):
            print '  ', c, f

    print

    if dirtyFit and exists(fitFile):
        print 'The .fit file contains changes that have not yet been staged for commit.'
        if noChanges:
            print 'If you want to include these changes in a commit, you should run "git-fit save"'
            print 'to properly stage the .fit file (DO NOT stage it directly with git-add).'
        else:
            print 'If you run "git-fit save" both the new changes shown above and the recorded'
            print 'changes in the current .fit file will be staged together.'
        print

    if len(untracked) > 0:
        print 'Changes currently include items that have been marked to be untracked from fit.'
        print 'Since a .gitattributes file must have been modified to do this, consider also'
        print 'making a parallel change to a .gitignore file if you haven\'t already.'
    if len(upstream) > 0:
        print ' * %s object(s) may need to be uploaded. Run \'git-fit put\' -s for details.'%len(upstream)
    if len(downstream) > 0:
        print ' * %d objects(s) will be skipped (based on extension)'%len(skippedFiles)
        print ' * %d object(s) need to be downloaded. Run \'git-fit get\' -s for details.'%len(downstream)
    if len(stubs) > 0:
        print ' * %d object(s) exist in the working tree as empty zero-byte stubs.'%len(stubs)
        print '   These objects are locally cached, so running \'git-fit restore\' will replace'
        print '   them with their cached contents (may not be up to date with remote storage).'


@gitDirOperation(repoDir)
def getTrackedItems():
    # The tracked items in the working tree according to the
    # currently set fit attributes
    fitSetRgx = re.compile('(.*): fit: set')
    p = popen('git ls-files -o'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    return {m.group(1) for m in [fitSetRgx.match(l) for l in p.stdout] if m}

@gitDirOperation(repoDir)
def getChangedItems(fitTrackedData, trackedItems=None, paths=None, pathArgs=None):

    # The tracked items according to the saved/committed .fit file
    expectedItems = set(fitTrackedData)
    trackedItems = trackedItems or getTrackedItems()

    # Get valid, fit-friendly repo paths from given arbitrary path arguments
    if paths == None and pathArgs:
        paths = getValidFitPaths(pathArgs, expectedItems | trackedItems, basePath=repoDir, workingDir=workingDir)

    if paths != None:
        if len(paths) == 0:
            return ({}, set(), set(), set(), set(), {}, {}) # return all 7 as empty
        expectedItems &= paths
        trackedItems &= paths

    # Use set difference and intersection to determine some info about changes
    # to the status of our items
    existingItems = expectedItems & trackedItems
    newItems = trackedItems - expectedItems
    missingItems = expectedItems - trackedItems

    # An item could be in missingItems for one of two reasons: either it
    # has been deleted from the working directory, or it has been marked
    # to not be tracked by fit anymore. We separate out these two sets
    # of missing items:
    untrackedItems = {i for i in missingItems if exists(i)}
    removedItems = missingItems - untrackedItems

    # Check all existing items for modification by comparing their expected
    # hash sums (those stored in the .fit file) to their new, actual hash sums.
    stats, stubs = updateStats(existingItems)
    modifiedItems = {i: [h,s[0]] for i,(h,s) in stats.iteritems() if h != fitTrackedData[i][0]}
    unchangedItems = existingItems - set(modifiedItems)

    return modifiedItems, newItems, removedItems, untrackedItems, unchangedItems, stats, stubs

@gitDirOperation(repoDir)
def getStagedOffenders():
    fitConflict = []
    binaryFiles = []

    staged = []
    p = popen('git diff --name-only --diff-filter=A --cached'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    for l in p.stdout:
        filepath = l[:l.find(':')]
        if l.endswith(' set\n'):
            fitConflict.append(filepath)
        elif l.endswith(' unspecified\n'):
            staged.append(filepath)

    if len(staged) > 0:
        binaryFiles = filterBinaryFiles(staged)

    return set(fitConflict), set(binaryFiles)

@gitDirOperation(repoDir)
def checkForChanges(fitTrackedData, paths=None, pathArgs=None):
    changes = getChangedItems(fitTrackedData, paths=paths, pathArgs=pathArgs)[:-3]
    if not any(changes):
        return
    
    return changes

@gitDirOperation(repoDir)
def restore(fitTrackedData, quiet=False, pathArgs=None):
    changes = checkForChanges(fitTrackedData, pathArgs=pathArgs)
    if not changes:
        if not quiet:
            print 'Nothing to restore (no changes detected).'
        return

    modified, added, removed, untracked = changes
    missing = restoreItems(fitTrackedData, modified, added, removed, quiet=quiet)
    if missing > 0:
        print restoreMissingMessage%missing

@gitDirOperation(repoDir)
def restoreItems(fitTrackedData, modified, added, removed, quiet=False):
    for i in sorted(added):
        remove(i)
        if not quiet:
            print 'Removed: %s'%i

    missing = 0
    touched = {}

    result = _restoreFromCache('Added', sorted(removed), fitTrackedData, quiet=quiet)
    touched.update(result[0])
    missing += result[1]
    result = _restoreFromCache('Restored', sorted(modified), fitTrackedData, quiet=quiet)
    touched.update(result[0])
    missing += result[1]

    refreshStats(touched)

    return missing

def _restoreFromCache(restoreType, objects, fitTrackedData, quiet=False):
    missing = 0
    touched = {}
    cached = cache.find(fitTrackedData[f][0] for f in objects)
    for filePath in objects:
        objHash = fitTrackedData[filePath][0]
        fileDir = dirname(filePath)
        fileDir and (exists(fileDir) or makedirs(fileDir))
        if objHash in cached:
            if not quiet:
                print '%s: %s'%(restoreType, filePath)
            copyfile(cached[objHash], filePath)
            touched[filePath] = objHash
        else:
            if not quiet:
                print '%s (empty): %s'%(restoreType, filePath)
            open(filePath, 'w').close()  #write a 0-byte file as placeholder
            touched[filePath] = 0
            missing += 1

    return (touched, missing)

@gitDirOperation(repoDir)
def save(fitTrackedData, paths=None, pathArgs=None, forceWrite=False, quiet=False):
    added,removed,stubs = saveItems(fitTrackedData, paths=paths, pathArgs=pathArgs, quiet=quiet)

    if stubs:
        print '\nerror: The following items are empty, zero-byte files and cannot be added to fit:\n'
        for i in sorted(stubs):
            print '  ',i
        print
        return False

    if len(added) + len(removed) > 0 or forceWrite:
        print 'Working-tree changes saved.'
        writeFitFile(fitTrackedData)

    fitFileStatus = getFitFileStatus()
    if len(fitFileStatus) == 0 or fitFileStatus[1] == ' ':
        return True

    oldStagedFitFileHash = None
    newStagedFitFileHash = None
    if fitFileStatus[0] == 'A':
        oldStagedFitFileHash = getStagedFitFileHash()
    popen('git add -f'.split()+[fitFile]).wait()
    newStagedFitFileHash = getStagedFitFileHash()
    print 'Staged .fit file.'

    if oldStagedFitFileHash != newStagedFitFileHash:
        _saveToCache(added, fitTrackedData, newStagedFitFileHash)

    return True

@gitDirOperation(repoDir)
def saveItems(fitTrackedData, paths=None, pathArgs=None, quiet=False):
    changes = checkForChanges(fitTrackedData, paths=paths, pathArgs=pathArgs)
    if not changes:
        if not quiet:
            print 'Nothing to save (no changes detected).'
        return {},set(),set()
    
    modified, added, removed, untracked = changes

    stats, stubs = updateStats(added, filePath=addedStatFile)
    modified.update((i,[h,s[0]]) for i,(h,s) in stats.iteritems())
    removed |= untracked

    fitTrackedData.update(modified)
    for i in removed:
        del fitTrackedData[i]

    return modified,removed,stubs

def _saveToCache(newItems, fitTrackedData, fitFileHash):
    toAdd = dict(newItems)
    toRemove = set()

    for l in listdir(savesDir):
        savesFile = joinpath(savesDir, l)
        oldSaveItems = readFitFile(savesFile)
        for i,f in oldSaveItems.iteritems():
            if fitTrackedData.get(i) == f:
                toAdd[i] = f
            else:
                toRemove.add(f[0])
        remove(savesFile)

    writeFitFile(toAdd, joinpath(savesDir,fitFileHash))
    cache.delete(toRemove - {toAdd[i][0] for i in toAdd})
    cache.insert({h:(s,f) for f,(h,s) in newItems.iteritems()}, progressMsg='Caching new and modified items')
