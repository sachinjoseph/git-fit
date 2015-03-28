from subprocess import Popen as popen, PIPE
from platform import system

# Below two lines prevents Python raising an exception
# when piping output to commands like less, head that
# can prematurely terminate the pipe. Disabling this in
# windows since windows does not have SIGPIPE
# https://docs.python.org/2/library/signal.html
if system() != "Windows":
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL) 

# Skip downstream transfer of certain files based on file extensions for individual users
# This can potentially save transfer of GBs of data on the disk and also over the network
# These skipped files will be still be tracked by git-fit, although it will remain as zero byte stubs on the particular local machine

# Consider two developers W [Windows user] and M [Mac user] working on a cross platform product. W would not probably need .a or .dylib files
# on his local machine for building. Similarly, M would not probably need .dll or .lib or .pdb or .exe files on his machine. Typically the size of
# dependencies on each platform would be in GBs (in my team's case it's about 12GB!). Now, if we have an option to skip files based on extension,
# it would reduce the bandwidth, time to download the (new) dependencies, and also local storage space!
# We could use path specific git-fit, but, this approach has two clear advantages:
# 1) The user could still upload files of any type (including skipped types) into any path
# 2) In cases where dependencies are not separable into different directories, can be used without modifying a lot of
#    paths (in source files, in build scripts, in dependency copy scripts, etc.)

# Configuration::
#   > git config fit.downstream.skipExtensions '.extensions .separated .by .spaces'
#     (if .dll is in the skip list, files a.dll and b.DLL will not be downloaded)
  
#   > git config fit.downstream.skipExtensionsCaseSensitive '.case .sensitive .extensions .separated .by .spaces'
#     (if .dll is in the skip list, file a.dll will not be downloaded, but file b.DLL will be downloaded)
    
# To unset skipExtensions, use
#   > git config --unset fit.downstream.skipExtensions
#   > git config --unset fit.downstream.skipExtensionsCaseSensitive

# Example configuration:
#   On a Windows machine, typically .a and .dylib files are not needed. This can be configured as:
#
#       > git config fit.downstream.skipExtensions '.a .dylib'
#   
#   Now, git-fit will not perform download of any .a or .dylib files from remote storage to that machine. The user will still be able to upload any types of files, including .a and .dylib.
#   Similarly, skipping of .dll, .lib, .pdb, etc. can be configured on a Mac/Linux machine to save a lot of bandwidth, and storage space.

# extensions in this list are compared case-insensitively, i.e., .DLL = .dll
downstreamSkipExtensionsCaseInsensitive = popen('git config fit.downstream.skipExtensions'.split(), stdout=PIPE).communicate()[0].split()

# extensions in this list are compared case-sensitively, i.e., .DLL != .dll
downstreamSkipExtensionsCaseSensitive = popen('git config fit.downstream.skipExtensionsCaseSensitive'.split(), stdout=PIPE).communicate()[0].split()
