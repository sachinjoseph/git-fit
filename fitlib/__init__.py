from subprocess import Popen as popen, PIPE
from os import stat, path, chdir, getcwd, close as osclose, remove, mkdir, devnull
from tempfile import mkstemp
from json import load, dump
from paths import fitMapToTree, fitTreeToMap
import re
import platform
from threading import Thread as thread
from sys import stdout
from gzip import GzipFile as gz
from StringIO import StringIO
from skipExtensions import downstreamSkipExtensionsCaseInsensitive, downstreamSkipExtensionsCaseSensitive

# Below two lines prevents Python raising an exception
# when piping output to commands like less, head that
# can prematurely terminate the pipe. Disabling this in
# windows since windows does not have SIGPIPE
# https://docs.python.org/2/library/signal.html
if platform.system() != "Windows":
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL) 


# Get the repo root directory if inside one, otherwise exit
_p = popen('git rev-parse --show-toplevel'.split(), stdout=PIPE)
repoDir = _p.communicate()[0].strip()
if _p.returncode != 0:
    raise Exception('Could not determine git working tree.')

# Get some more directory/file paths we're interested in
selfDir = path.dirname(path.realpath(__file__))
workingDir = getcwd()
gitDir = popen('git rev-parse --git-dir'.split(), stdout=PIPE).communicate()[0].strip()
fitDir = path.join(gitDir,'fit')
fitFile = path.join(repoDir, '.fit')
cacheDir = path.join(fitDir, 'cache')
objectsDir = path.join(cacheDir, 'objects')
savesDir = path.join(cacheDir, 'saves')
commitsDir = path.join(cacheDir, 'commits')
lruFile = path.join(cacheDir, 'lru')
statFile = path.join(fitDir, 'stat')
addedStatFile = path.join(fitDir, 'stat.added')
mergeMineFitFile = path.join(fitDir, 'merge-mine')
mergeOtherFitFile = path.join(fitDir, 'merge-other')
tempDir = path.join(fitDir, 'temp')
fitManifestItemsTempDir = path.join(fitDir, 'manifest_items_tmp')

_fitFileItemRgx = re.compile('([^:]+):\[([^,]+),(\d+)\],?')
zeroByteSha1 = 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'

# Parameterized decorator that will wrap the decoratee with a cd into the git directory
# before running the operation, and a cd back into the starting directory afterwards.
# The parameterized form should be used for methods that that are not class members or
# to tell the decorator to use a specific directory as the git directory. The basic
# form should be used only for class member methods where the class also has a
# string self.gitDir member.
def gitDirOperation(arg):
    # "arg" will be either a callable, or a string, depending on how the decorator is used.
    # If the decorator is used as @gitDirOperation, it is used in the basic way and is NOT
    # parameterized. It is parameterized if called with a string, such as
    # @gitDirOperatio('path/gitFolder'). How we get the git directory depends on which
    # form of the decorator is used.

    isParameterized = isinstance(arg, basestring)
    getDir = (lambda s: arg) if isParameterized else (lambda s: s[0].gitDir)

    # Assume non-parameterized form by default. If actually the parameterized form
    # is used, than wrapper() will set decoratee to the passed-in function, which
    # is the actual decoratee
    decoratee = [arg]

    def decorator(*args, **kwargs):
        cwd = getcwd()
        chdir(getDir(args))

        retval = decoratee[0](*args, **kwargs)

        chdir(cwd)
        return retval

    def wrapper(func):
        decoratee[0] = func
        return decorator

    return wrapper if isParameterized else decorator

def fitStats(filename):
    stats = stat(filename)
    return stats.st_size, stats.st_mtime, stats.st_ctime, stats.st_ino

def readFitFile(filePath=fitFile, rev=None):
    if rev:
        fitDataString = _getFitDataStringForRev(rev=rev)
        try:
            return load(gz(None,None,None,StringIO(fitDataString)))
        except:
            return fitTreeToMap(_readFitFileRec(StringIO(fitDataString)))
    elif not (path.exists(filePath) and path.getsize(filePath) > 0):
        return {}
    else:
        try:
            return load(gz(filePath))
        except:
            fitFileIn = open(filePath)
            fitData = fitTreeToMap(_readFitFileRec(fitFileIn))
            fitFileIn.close()
            return fitData
    
def _readFitFileRec(fitFileIn):
    items = {}
    for l in fitFileIn:
        l = l.strip()
        if l.endswith('{'):
            items[l.split(':')[0]] = _readFitFileRec(fitFileIn)
        elif l in ('}', '},') :
            break
        else:
            parts = list(_fitFileItemRgx.match(l).groups())
            items[parts[0]] = [parts[1], int(parts[2])]
    return items

def writeFitFile(fitData, filePath=fitFile):
    fitFileOut = open(filePath, 'wb')
    _writeFitFileRec(fitFileOut, fitMapToTree(fitData))
    fitFileOut.close()

def _dictItemComparator(a,b):
    if type(a[1]) == type(b[1]):
        return -1 if a[0] < b[0] else (1 if a[0] > b[0] else 0)
    if type(a[1]) == type({}):
        return 1
    return -1

def _writeFitFileRec(fitFileOut, fitData):
    if len(fitData) == 0:
        return

    items = sorted(fitData.iteritems(), cmp=_dictItemComparator)
    for k,v in items[:-1]:
        _writeFitFileItem(fitFileOut, k, v)
    k,v = items[-1]
    _writeFitFileItem(fitFileOut, k, v, sep='')

def _writeFitFileItem(fitFileOut, k,v, sep=','):
    if type(v) == type({}):
        print >>fitFileOut, '%s:{'%k
        _writeFitFileRec(fitFileOut, v)
        print >>fitFileOut, '}'+sep
    else:
        print >>fitFileOut, ('%s:[%s,%s]'+sep)%(k,v[0],v[1])

def printAsText(fitData):
    items = sorted([(b[:7],a) for a,(b,c) in  fitData.iteritems()], key=lambda i:i[1])
    print '\n'.join(['%s %s'%(h,p) for h,p in items])

# The stat file is a Python-pickled dictionary of the following form:
#   {filename --> (st_size, st_mtime, st_ctime, st_ino, checksum_hash)}
def readStatFile(filePath=statFile):
    return load(open(filePath)) if path.exists(filePath) else {}

def writeStatFile(stats, filePath=statFile):
    statOut = open(filePath, 'wb')
    dump(stats, statOut)
    statOut.close()

def _gitHashInputProducer(stream, items):
    for j in items:
        print >>stream, j
        stream.flush()
    stream.close()

@gitDirOperation(repoDir)
def computeHashes(items):
    if not items:
        return []

    hashes = []
    numItems = len(items)
    numDigits = str(len(str(numItems)+''))
    progress_fmt = ('\rComputing hashes for new objects...%6.2f%%  '+'%'+numDigits+'s/%'+numDigits+'s')
    print progress_fmt%(0, 0, numItems),
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    thread(target=_gitHashInputProducer, args=(p.stdin,items)).start()
    i = 0
    for l in p.stdout:
        hashes.append(l.strip())
        i += 1
        print progress_fmt%(i*100./numItems, i, numItems),
        stdout.flush()
    print '\r'+(' '*(45+int(numDigits)*2))+'\r',
    return hashes

@gitDirOperation(repoDir)
def refreshStats(items, filePath=statFile):
    stats = readStatFile(filePath=filePath)
    for i in items:
        stats[i] = (items[i], fitStats(i))
    writeStatFile(stats, filePath=filePath)

@gitDirOperation(repoDir)
def updateStats(items, filePath=statFile):
    oldStats = readStatFile(filePath=filePath)
    newStats = {}
    stubs = []
    skippedFiles = []
    for i in items:
        stats = fitStats(i)
        if stats[0] > 0:
            newStats[i] = stats
        else:
            # compare the extension with the skipExtensions list, and add to stubs only if required.
            if path.splitext(i)[-1].lower() in map(str.lower, downstreamSkipExtensionsCaseInsensitive) or path.splitext(i)[-1] in downstreamSkipExtensionsCaseSensitive:
                skippedFiles.append(i)
            else:
                stubs.append(i)

    # An item is "touched" if its cached stats don't match its new stats.
    # "Touched" is a necessary but not sufficient condition for an item to
    # be considered "modified". Modified items are those that are touched
    # AND whose checksums are different, so we do checksum comparisons next
    touched = [i for i,s in newStats.iteritems() if i not in oldStats or tuple(oldStats[i][1]) != s]
    touched = dict(zip(touched, computeHashes(touched)))

    statsUpdated = False
    if len(touched) > 0:
        statsUpdated = True
        for i,h in touched.iteritems():
            oldStats[i] = (h,newStats[i])
    if len(newStats) != len(oldStats):
        statsUpdated = True
        for s in set(oldStats) - set(newStats):
            del oldStats[s]
    if statsUpdated:
        writeStatFile(oldStats, filePath=filePath)

    return oldStats, stubs

def getFitSize(fitTrackedData):
    return sum(int(s) for p,(h,s) in fitTrackedData.iteritems())

def getCommitFile(rev=None):
    if not path.exists(commitsDir):
        mkdir(commitsDir)
    return path.join(commitsDir, rev or getHashForRevision() or '---')

def getHashForRevision(rev='HEAD'):
    return popen(('git rev-parse %s'%rev).split(), stdout=PIPE, stderr=open(devnull, 'wb')).communicate()[0].strip()

@gitDirOperation(repoDir)
def _getFitDataStringForRev(rev):
    return popen(('git show %s:.fit'%rev).split(), stdout=PIPE, stderr=open(devnull, 'wb')).communicate()[0]

@gitDirOperation(repoDir)
def getFitManifestChanges(rev='HEAD@{1}'):
    lines = popen(("git diff-tree -r --name-only %s HEAD -- *.gitattributes .fit"%rev).split(), stdout=PIPE, stderr=open(devnull, 'wb')).communicate()[0].strip()
    return lines.split('\n') if lines else []

@gitDirOperation(repoDir)
def dirtyGitItemsFilter(items):
    lines = popen('git status --porcelain -u --ignored'.split() + list(items), stdout=PIPE).communicate()[0].rstrip()
    return [l.split(None, 1)[1] for l in lines.split('\n')] if lines else []

@gitDirOperation(repoDir)
def getStagedFitFileHash():
    return popen('git ls-files -s .fit'.split(), stdout=PIPE).communicate()[0].strip().split()[1]

@gitDirOperation(repoDir)
def getFitFileStatus():
    return popen('git status --porcelain -u --ignored .fit'.split(), stdout=PIPE).communicate()[0].rstrip()

@gitDirOperation(repoDir)
def filterBinaryFiles(files):
    binaryFiles = []

    p = popen('file -f -'.split(), stdout=PIPE, stdin=PIPE)
    fileTypes = p.communicate('\n'.join(files))[0].strip().split('\n')

    for f in fileTypes:
        sepIdx = f.find(':')
        filepath = f[:sepIdx]
        if f.find('text', sepIdx) < 0:
            binaryFiles.append(filepath)

    return binaryFiles

class DataStore:
    def __init__(self, progress):
        pass
    def check(self, dst):
        return None
    def get(self, src, dst, size):
        return False
    def put(self, src, dst, size):
        return False
    def close(self):
        pass
