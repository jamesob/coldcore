## Installation on macOS

Want to use coldcore but don't have much (or any) commandline experience? No problem!
This guide is intended to be usable by people without much CLI know-how.

### Installing and configuring Bitcoin Core

1. [Download Bitcoin Core](https://bitcoin.org/en/download) and install it. 
   You might want to read the [full node guide](https://bitcoin.org/en/full-node). If
   you're serious, be sure to validate the signatures of what you download. This is the
   only way to know if you're running the Bitcoin that you expect.
1. Start Bitcoin. It will begin syncing.
1. **Note:** if you previously had Bitcoin Core installed, ensure it is at least
   version 0.19. Coldcore relies on features in at least this version.
1. Open the Preferences in Bitcoin Core (`⌘+,`).  
![prefs](/docs/img/01-prefs.png)
1. Edit the configuration file  
![conf](/docs/img/02-open-config.png)
1. Insert the lines
    ```
    server=1
    ```
    to enable the RPC server - this is how coldcore will communicate with Bitcoin Core.
    
    *Advice:* for a faster initial block download, specify the `dbcache` setting according
    to how much free memory you can devote to Bitcoin. For example, if you want to allow
    Core to use 2GB, add the line
    ```
    dbcache=2000
    ```

    *Note:* if you're testing, you can also insert the line
    ```
    testnet=1
    ```
    ![edit](/docs/img/03-conf.png)
1. Ensure you save the configuration file.
1. Restart Bitcoin for the new configuration to take effect.

### Opening a terminal

Now, open a Terminal by pressing `⌘+space` and typing "Terminal". You should see
the Terminal.app icon selected; press enter.

Don't be scared of the terminal; it's sort of like being in a slightly more technical
version of Finder, but you can run programs and other useful stuff.

For a very quick introduction to the command line, [give this article a
read](https://blog.teamtreehouse.com/introduction-to-the-mac-os-x-command-line).
Or if you prefer videos, [give this a watch](https://www.youtube.com/watch?v=aKRYQsKR46I).

### If you have your Bitcoin data in a nonstandard location...

for example, if you're using an external device to host your Bitcoin data. If this is
the case, we need to set up some filesystem shortcuts so that coldcore can find your
data.

The first step is figuring out the "absolute path" of your datadir. This is basically
a complete location for where your data is on the harddrive. 

To do this,
- navigate to where your Bitcoin datadir is in Finder,
- `ctrl + (right click)` the folder,
- hold the `Option` key, then select `Copy "yourdirname" as Pathname`

Now that the absolute path to your datadir is on the clipboard, we can use it
to set up the shortcut so that coldcore can find your data. Jump back into
the terminal, and type

```sh
$ ln -s [press ⌘+v to paste] ~/Library/Application\ Support/Bitcoin
```

So the actual command should look something like
```sh
$ ln -s /absolute/path/to/your/hd/datadir ~/Library/Application\ Support/Bitcoin
```
For example, if your external volume is named `FOOBAR` and your Bitcoin data directory 
is stored in a folder called `datadir`, this command might be
```sh
$ ln -s /Volumes/FOOBAR/datadir ~/Library/Application\ Support/Bitcoin
```
Doing this allows coldcore to autodetect your RPC credentials.


### Checking Python

Now we have to make sure that you have the right Python version installed.

In your terminal, run 

```sh
$ python3 --version
```

If you see a version number at or above `3.7`, you're good to go! You have everything
you need to run coldcore.

If not, [go install brew](https://brew.sh/) and then run 
```sh
$ brew install python3
```

and then repeat the python3 version check after the installation has completed.


### Getting coldcore

Now we're going to use a tool called `git`, which is a way that developers manage
changes to source code. You can read more about git [here](https://www.educative.io/edpresso/what-is-git).

In the terminal, type
```sh
$ git clone https://github.com/jamesob/coldcore.git
```

Some text should whiz by. Now change directories (`cd`) into the coldcore folder:
```sh
$ cd coldcore
```

and check coldcore's version:
```sh
$ ./coldcore --version
```

If this printed something out that looks reasonable, congratulations! You're set up with
coldcore and ready to go. 

Start setup with 
```sh
$ ./coldcore
```

### Running coldcore

Whenever you want to run coldcore, just open a terminal and type the following commands:

```sh
$ cd coldcore
$ ./coldcore
```


### Verifying the release

By default, when you run that `git` command, you get the latest development
version of coldcore. That means there may be recent changes that I haven't yet signed.
This might prevent you from verifying the integrity of the script (because I haven't 
been able to generate signatures, which is part of the release process). 

This means you're getting the latest changes, but they may not be fully tested.

If you want to switch to a stable version for which you can verify signatures, open a terminal 
and run 
```sh
$ cd coldcore
$ git checkout stable
```

Now you should be able to verify signatures as mentioned in the README. You may need to
install `gpg` first:
```sh
$ brew install gpg2
```

After that, here's the short version of verification (see README for more details):
```sh
# Have your GPG learn my pubkey
$ gpg --keyserver keyserver.ubuntu.com --recv-keys 0x25F27A38A47AD566

# Retrieve the signed hash of your coldcore version
$ curl -O http://img.jameso.be/sigs/coldcore-$(./coldcore --version).asc

# Have GPG check the signature of the hash
$ gpg coldcore-[version].asc

# Ensure these two commands output the same hash:
$ cat coldcore-[version].asc
$ sha256sum coldcore
```
