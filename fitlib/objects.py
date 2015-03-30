from . import gitDirOperation, refreshStats, getFitSize, readFitFile, writeFitFile, getCommitFile, commitsDir
from . import repoDir, fitDir, objectsDir, tempDir, workingDir
from paths import getValidFitPaths
import cache
from subprocess import Popen as popen, PIPE
from os.path import dirname, basename, splitext, exists, join as joinpath, getsize
from os import walk, makedirs, remove, close as osclose, mkdir, listdir, stat
from shutil import copyfile, move
from sys import stdout
from tempfile import mkstemp
from skipExtensions import downstreamSkipExtensionsCaseInsensitive, downstreamSkipExtensionsCaseSensitive

def getDataStore(progressCallback):
    moduleName = popen('git config fit.datastore.moduleName'.split(), stdout=PIPE).communicate()[0].strip()
    modulePath = popen('git config fit.datastore.modulePath'.split(), stdout=PIPE).communicate()[0].strip()

    if not moduleName:
        raise Exception('error: No external data store is configured. Check the fit.datastore keys in git config.')

    if modulePath:
        import sys
        sys.path.append(modulePath)

    try:
        from importlib import import_module
        return import_module(moduleName).Store(progressCallback)
    except Exception as e:
        print 'error: Could not load the data store configured in fit.datastore.'
        raise

def getUpstreamItems():
    cachedCommits = cache.getCommittedObjects()
    return set(f for f,(h,s) in readFitFile(getCommitFile()).iteritems() if h in cachedCommits)

def getDownstreamItems(fitTrackedData, paths, stats):
    cached = cache.find((fitTrackedData[p][0] for p in paths), update=False)
    skippedFiles = []
    downstreamItems = [p for p in paths if not (p in stats or fitTrackedData[p][0] in cached or True if (splitext(p)[-1] not in downstreamSkipExtensionsCaseSensitive) else True if (splitext(p)[-1] not in map(str.lower, downstreamSkipExtensionsCaseInsensitive)) else False, skippedFiles.append(p))]
    return downstreamItems, skippedFiles

class _ProgressPrinter:
    def __init__(self):
        self.size_total = 0
        self.size_item = 0
        self.size_done = 0
        self.item_name = ''
        self.item_started = False

    def updateProgress(self, done, size, custom_item_string=None):
        if custom_item_string:
            fmt_args = (
                (self.size_done+done)*100./self.size_total,
                custom_item_string,
                self.item_name
            )
            print '\rOverall: %6.2f%%    %s   %s'%fmt_args,
        else:
            fmt_args = (
                (self.size_done+done)*100./self.size_total,
                self.size_item/1048576.,
                done*100./size,
                self.item_name
            )
            print '\rOverall: %6.2f%%    %7.3f MB   %6.2f%%   %s'%fmt_args,
        stdout.flush()
        self.item_started = True
    def newItem(self, name, size):
        if self.size_item and self.item_started:
            print

        self.size_done += self.size_item
        self.item_name = name
        self.size_item = size
        self.item_started = False

    def done(self):
        if self.size_item > 0:
            self.size_done += self.size_item
            print

    def setTotalSize(self, totalSize):
        self.size_total = totalSize

class _QuietProgressPrinter:
    def updateProgress(self, done, size):
        pass
    def newItem(self, name, size):
        pass
    def done(self):
        pass
    def setTotalSize(self, totalSize):
        pass

@gitDirOperation(repoDir)
def get(fitTrackedData, pathArgs=None, summary=False, showlist=False, quiet=False):    
    allItems = fitTrackedData.keys()
    validPaths = getValidFitPaths(pathArgs, allItems, basePath=repoDir, workingDir=workingDir) if pathArgs else allItems

    needed = []   # not in working tree nor in cache, must be downloaded
    touched = {}
    skippedFiles = [] # these files will not be transferred downstream, because they are configured to be skipped based on extension

    cached = cache.find(fitTrackedData[f][0] for f in validPaths)
    for filePath in validPaths:
        objHash, size = fitTrackedData[filePath]
        if exists(filePath) and getsize(filePath) == 0:
            objPath = cached.get(objHash)
            fileDir = dirname(filePath)
            fileDir and (exists(fileDir) or makedirs(fileDir))
            if objPath:
                copyfile(objPath, filePath)
                touched[filePath] = objHash
            else:
                if splitext(filePath)[-1].lower() in map(str.lower, downstreamSkipExtensionsCaseInsensitive) or splitext(filePath)[-1] in downstreamSkipExtensionsCaseSensitive:
                    skippedFiles.append((filePath, objHash, size))
                else:
                    needed.append((filePath, objHash, size))

    totalSize = sum([size for f,h,size in needed])
    totalSkippedSize = sum([size for f,h,size in skippedFiles])

    if len(needed) == 0 and len(skippedFiles) == 0:
        if not quiet:
            print 'No tranfers needed! %s items retrieved from cache and the rest already exist.'%len(touched)
            print '%s downstream transfers skipped based on extension.'%len(skippedFiles)
    elif showlist:
        # either needed or skippedFiles or both are empty if program control reaches here
        if len(skippedFiles) > 0:
            print
            for filePath,h,size in sorted(skippedFiles):
                print '  %6.2fMB  %s (skipped)'%(size/1048576, filePath)
            
            print '\nThe above objects will be skipped (based on extension).'
            print 'Total tranfer size (skipped): %.2fMB'%(totalSkippedSize/1048576)
        
        if len(needed) > 0:
            print
            for filePath,h,size in sorted(needed):
                print '  %6.2fMB  %s'%(size/1048576, filePath)
                
            print '\nThe above objects can be tranferred (total transfer size: %.2fMB).'%(totalSize/1048576)
            print 'You may run git-fit get to start the transfer.'
            
    elif summary:
        print len(validPaths), 'items are being tracked'
        if (len(needed) + len(skippedFiles)) > 0:
            print (len(needed) + len(skippedFiles)), 'of the tracked items are not cached locally (%.2fMB)'%((totalSkippedSize + totalSize) / 1048576.0)
            print
            if len(skippedFiles) > 0:
                print '%s downstream transfers will be skipped (based on extension, %.2fMB).'%(len(skippedFiles), totalSkippedSize/1048576.0)
            if len(needed) > 0:
                print len(needed), 'of the tracked items need to be downloaded (%.2fMB)'%(totalSize/1048576.0)
            print 'Run \'git-fit get -l\' to list these items.'
            
        if len(needed) == 0:
                print '\nNo transfers required.'
    else:
        successes = []
        _transfer(_get, needed + skippedFiles, totalSize + totalSkippedSize, fitTrackedData, successes, quiet)

        for filePath, objHash, size in successes:
            touched[filePath] = objHash

    refreshStats(touched)

def _get(items, store, pp, successes, failures):
    if not exists(tempDir):
        mkdir(tempDir)
    
    skippedFiles = []
    for filePath,objHash,size in items:
        if splitext(filePath)[-1].lower() in map(str.lower, downstreamSkipExtensionsCaseInsensitive) or splitext(filePath)[-1] in downstreamSkipExtensionsCaseSensitive:
            pp.newItem(filePath, size)
            pp.updateProgress(size, size, custom_item_string='Skipped')
            skippedFiles.append(filePath)
            continue
        pp.newItem(filePath, size)
        
        # Copy download to temp file first, and then to actual object location
        # This is to prevent interrupted downloads from causing bad objects to be placed
        # in the objects cache
        (tempHandle, tempTransferFile) = mkstemp(dir=tempDir)
        osclose(tempHandle)
        key = store.check('%s/%s'%(objHash[:2], objHash[2:]))

        try:
            transferred = store.get(key, tempTransferFile, size)
        except:
            transferred = False
        if key and transferred:
            pp.updateProgress(size, size)
            popen(['mv', tempTransferFile, filePath]).wait()
            successes.append((filePath, objHash, size))
        else:
            pp.updateProgress(size, size, custom_item_string='ERROR')
            failures.append(filePath)

    cache.insert({h:(s,f) for f,h,s in successes}, inLru=True, progressMsg='Caching newly gotten items')

@gitDirOperation(repoDir)
def put(fitTrackedData, pathArgs=None, force=False, summary=False,  showlist=False, quiet=False):
    commitsFile = getCommitFile()
    commitsFitData = readFitFile(commitsFile)
    available = [(f, o, s) for f,(o, s) in commitsFitData.iteritems()]
    totalSize = sum([size for f,h,size in available])

    if len(available) == 0:
        if not quiet:
            print 'No tranfers needed! There are no cached objects to put in external location for HEAD.'
    elif showlist:
        print
        for filePath,h,size in available:
            print '  %6.2fMB  %s'%(size/1048576, filePath)
        print '\nThe above objects can be tranferred (maximum total transfer size: %.2fMB).'%(totalSize/1048576)
        print 'You may run git-fit put to start the transfer.'
    elif summary:
        print len(fitTrackedData), 'items are being tracked'
        print len(available), 'of the tracked items MAY need to be sent to external location'
        print '%.2fMB maximum possible transfer size'%(totalSize/1048576)
        print 'Run \'git-fit put -l\' to list these items.'
    else:
        successes = []
        _transfer(_put, available, totalSize, fitTrackedData, successes, quiet)

        for filePath, objHash, size in successes:
            del commitsFitData[filePath]

    if len(commitsFitData) > 0:
        writeFitFile(commitsFitData, commitsFile)
    elif exists(commitsFile):
        remove(commitsFile)
    for f in sorted(listdir(commitsDir), key=lambda x: stat(joinpath(commitsDir, x)).st_mtime)[:-2]:
        remove(joinpath(commitsDir, f))

def _put(items, store, pp, successes, failures):
    cached = cache.find(o for f,o,s in items)
    for filePath,objHash,size in items:
        pp.newItem(filePath, size)
        if objHash not in cached:
            pp.updateProgress(size, size, custom_item_string='ERROR')
            failures.append(filePath)
            continue

        done = True
        keyName = '%s/%s'%(objHash[:2], objHash[2:])
        if store.check(keyName):
            pp.updateProgress(size, size, custom_item_string='No transfer needed.')
        else:
            try:
                transferred = store.put(cached[objHash], keyName, size)
            except:
                transferred = False
            if transferred:
                pp.updateProgress(size, size)
            else:
                done = False
                pp.updateProgress(size, size, custom_item_string='ERROR')
                failures.append(filePath)
        if done:
            successes.append((filePath, objHash, size))

    cache.enque(o for f,o,s in successes)

def _transfer(method, items, size, fitTrackedData, successes, quiet):
    pp = _QuietProgressPrinter() if quiet else _ProgressPrinter()
    pp.setTotalSize(size)
    try:
        store = getDataStore(pp.updateProgress)
    except Exception as e:
        print e
        return

    failures = []
    items.sort()

    method(items, store, pp, successes, failures)

    pp.done()
    store.close()

    if len(failures) > 0:
        print '\n'.join(failures)
        print 'Above items could not be transferred.'

    fitSize = getFitSize(fitTrackedData)
    cacheSize = cache.size()[0]
    if cacheSize > fitSize * 2:
        print 'Cache size (%.2fMB) is larger than twice the tracked size (%.2fMB). Pruning...'%(cacheSize/1048576., fitSize/1048576.)
        cache.prune(fitSize * 2)
    else:
        print 'Cache size is %.2fMB and tracked size is %.2fMB (will not prune at this time).'%(cacheSize/1048576., fitSize/1048576.)
