## INTRODUCTION


`git-fit` helps your `git` repo stay fit and slim and keep `git` commands running fast. It lets you offload bloat (binary files) away from the repo and into some external location, committing instead only a single, small file with pointers into the external location. Integration with `git` through hooks, `fit` takes care of most things automatically behind the scenes. Other than that, there are only the below few commands you need to know in order to stay fit. ALL of these commands operate only on the HEAD revision that the repository currently points to. The commands, with the full set of options, are:
<pre>
git-fit         [--legend] [--all] [&lt;PATH&gt;...]
    -l, --legend    Print a legend showing what status symbols mean.
    -a, --all       List even those items whose status is unchanged.
</pre>  
Shows the `fit` state of the working tree and any detected problems.
<pre>
git-fit save    [&lt;PATH&gt;...]
</pre>
Updates `.fit` file with current changes to `fit` items in the working tree. The `.fit` file will also be `git`-added (which you can then commit along with any other non-`fit` changes). After running this command, any items that were shown as modified, added, removed, or untracked (*, +, -, ~) by the status output of `git-fit` will no longer be shown as such, since those changes will have been saved in the `.fit` file. However, any potential commit-aborting items will continue to be shown in the status.
<pre>
git-fit restore [&lt;PATH&gt;...]
</pre>
Discards any changes to `fit` items in the working tree. (THIS CANNOT BE UNDONE). Notice that this operation is the opposite of the save operation. This will IRREVERSIBLY discard all uncommitted changes to your `fit`-tracked items, bringing your working tree to a pristine condition with respect to those objects currently being tracked by `fit` (so use this command with caution). In other words, whatever modified, added, or removed (*, +, -) items you see in the `git-fit` status output before running restore, you will no longer see after running restore. Items marked to be untracked from `fit` (~) and any potential commit-aborting items will continue to be shown and cannot be "restored".
<br />
<pre>
git-fit get     [--summary] [--list] [--quiet] [&lt;PATH&gt;...]
    -s, --summary   Do not transfer. Instead, show a summary of what would be transferred.
    -l, --list      Do not transfer. Instead, list all the items that would be transferred.
    -q, -quiet      Suppress transfer progress output.
</pre>
Copies objects FROM remote location and/or populates working tree. Until this is done, any action in your project that requires the actual contents of these items will not work as expected. Only items that are not already in the working tree or local `fit` cache will be downloaded.
<br />
<pre>
git-fit put     [--summary] [--list] [--quiet]
</pre>
Copies objects TO remote location from local cache. Until this is done, people who are using your commits will not have access to these items. If an item already exist in the external store due to a previous upload (either by you or someone else), the item will be skipped (but this cannot be determined without actually starting the upload process first). Unlike `git-fit get`, `git-fit put` does not take optional `PATH` arguments -- all items needing to be uploaded for the HEAD must be uploaded to fulfill the commit.

### OTHER TOOLS
There are other tools that are designed to solve the same problem. The following tools have varying features/functionalities and all use `git`'s clean and smudge filters to seamlessly integrate with `git` commands.

<pre>
git-exile
git-bin
git-fat
git-media
</pre>
However, `git`'s clean/smudge filters force each filtered item to be fully read in from `stdin` and the transformations to be written to `stdout`. The side-effect is that these filters end up causing some basic and frequent `git` commands (such as `status`) to become really slow, countering the problem the tools were intended to help with in the first place. A small experiment will show that a super simple "clean = cat" filter applied to a directory containing about 200MB of images can cause `git status` to run 7x slower than without the filter applied (about 4.3s versus 0.6s). Besides this, there are other issues with some of the tools, like too many dependencies, inflexible storage locations, inactivity/abandonment, etc. If `git`'s clean/smudge filters did work efficiently though, then `git-exile` would probably be the best choice, and `git-fit` would probably have not been written. (There is also the `git-annex` tool and it does not currently use clean and smudge filters, but it has other major differences with the design goals of `git-fit`.)


## HOW IT WORKS
Unlike the tools above, the only way `git-fit` transparently integrates with the `git` system is through hooks (and not through clean/smudge filters). So, unless it is invoked through any of the five available commands, `fit` will just stay out of your way until commit or checkout. The trade-off resulting from this alternative setup is that that commands like `git status` or `git diff` will not be directly aware of the true state of `fit`-managed items. `git-fit` sacrifices this convenience in favor of speed and efficiency.

### What `fit` WILL handle
(1) Items you've TOLD `fit` to track. <br />
See [Configuration](https://github.com/sachinjoseph/git-fit/blob/master/README.MD#configuration). `fit` will detect changes in these items and offload them to your specified external location.

(2) Untracked binary files that are staged for `commit` into `git`. <br />
For any binary file that is added to `git` and `fit` has not been told about, a `git commit` including that binary file will cause that commit to be aborted. `fit` must be told to either ignore these items or track them. This enforcement is a feature intended to prevent accidental commits of items that should actually be handled by `fit`.

### What `fit` WILL NOT handle
(1) Items you've TOLD `fit` to ignore. <br />
See [Configuration](https://github.com/sachinjoseph/git-fit/blob/master/README.MD#configuration). `fit` will just pretend these items are not there.

(2) Items committed to the repo and already tracked by `git`. <br />
`fit` will NEVER touch items that have already been committed into `git`, never, no exceptions. Items being tracked by `fit` now somehow committed into `git` repo? `fit` will stop tracking it. There's an item already committed to `git`, and you're now asking fit to handle it? Well, it won't. For `fit` to handle something, the first requirement is that it must not be already tracked by `git`. If there is such an item that you need `fit` to handle instead, it must first be untracked from `git` by doing something like `git remove`.

## CONFIGURATION
###Initial one-time setup
Initial set-up to enable git-fit on your repo requires two steps:
(* NOTE: do not run "git fit" if you are already using any of the following hooks for your own
purpose: pre-commit, post-commit, post-checkout, or post-merge. See
more details [below](https://github.com/sachinjoseph/git-fit/#note-about-existing-git-hooks-in-your-repo-) regarding this.)
    
    (1) Add the git-fit root directory to your PATH
    (2) Run "git fit" inside your repo

Running "git-fit" by itself normally just shows the status, but the first time it is run on a newly cloned repo, it also initializes the repo for `fit` use.


### Instructing `fit` with include/exclude rules
Once initial setup is complete, you need to sprinkle `.gitattributes` and `.gitignore` files around your working tree (or update them), depending on which files you need to include or exclude from `git-fit`. See the [gitignore help page](http://git-scm.com/docs/gitignore) to learn how to specify patterns to match and select files (`.gitattributes` files use the same pattern syntax as `.gitignore` files). Here is a simple, common use-case example, which will include all `PNG` images in the directory and its sub-directories to be handled by `git-fit`:
<pre>
*.png fit
</pre>
To explicitly exclude files from `fit`, you would have in `.gitattributes` something like the following (notice the minus sign prefixed to the `fit` attribute):
<pre>
*.jar -fit
</pre>
This would allow all the jar files in the directory to be ignored by `fit` and committed through the normal `git` commit flow if desired, and `fit` will not complain about these items even though they are binary.

### Instructing `fit` to skip downloading files (based on extension) on specific machines
You can configure `fit` to skip downloading files based on extension on specific machines. **These files will still be tracked by `fit` and can be downloaded on a different machine (with `skipExtensions` not set)**. Uploading of files or files existing in cache are not affected by this; user will still be able to upload files of any extension.
<pre>
git config fit.downstream.skipExtensions '.extensions .separated .by .spaces'
git config fit.downstream.skipExtensionsCaseSensitive '.case .sensitive .extensions .separated .by .spaces'
</pre>

`skipExtensions`: performs `case-insensitive` comparison of file extensions. Having `.dll` in the skipExtensions will skip downloading files `a.dll` and `b.DLL`.

`skipExtensionsCaseSensitive`: performs `case-sensitive` comparision of file extensions. Having `.dll` in the skipExtensionsCaseSensitive will skip downloading file `a.dll`, but will download file `b.DLL`.

These 'skips' can be modified any time. Just edit the `config` file:
<pre>
git config --edit
</pre>

To unset these 'skips' completely, use:
<pre>
git config --unset fit.downstream.skipExtensions
git config --unset fit.downstream.skipExtensionsCaseSensitive
</pre>
Example configuration:
  On a Windows machine, typically `.a` and `.dylib` files are not required. This can be configured as:

    # typically on Windows, skips downloading Mac binaries
    git config fit.downstream.skipExtensions '.a .dylib'
  
  Now, `fit` will not download any `.a` or `.dylib` files on that machine. The user will still be able to upload any types of files, including `.a` and .`dylib.` Similarly, skipping of `.dll`, `.lib`, `.pdb`, etc. can be configured on a `*nix` machine to save a lot of bandwidth, and storage space:

    # typically on *nix, skips downloading Windows binaries
    git config fit.downstream.skipExtensions '.dll .exe .lib .pdb'
    
-----------
### Note about existing `git` hooks in your repo <br />
If you already have any of the these hooks doing other things, setup might be a little less straightforward. Someone with knowledge about the existing hooks in your repo should follow the direction below to add `fit` into your existing hooks. For all the `git` commands shown below, NEVER RUN THEM DIRECTLY yourself. They are only meant to be used as hooks.

#### The PRE-COMMIT hook <br />
Your hook executable will need to run:
<pre>git fit --pre-commit</pre>

#### The POST-COMMIT hook <br />
Your hook executable will need to run:
<pre>git fit --post-commit</pre>

#### The POST-CHECKOUT hook <br />
Your hook executable will need to run:
<pre>git fit --post-checkout &lt;ARG1&gt; &lt;ARG2&gt; &lt;ARG3&gt;</pre>
The ARGs are positional command line arguments that `git` passes to the hook executable and `git-fit` uses them. If your hook executable is simply a shell script, the ARGs can be specified as $1 $2 $3.
