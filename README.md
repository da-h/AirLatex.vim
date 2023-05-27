# AirLatex.vim

**Current State**: Use at your own risk.
What's the worst that can happen?
Something breaks and automatically clears the buffer. You can easily recover
this with the version history in overleaf, but it's still a pain, and might
mess up your comment positions. This has only happened to me once when actively
developing this plugin, but it's worth noting here.

As is, this is customized to my workflow- with no added hooks for broader
customization. If you'd like to add some, please create a PR- this is a won't fix for me.

<p align="center">
  <img src="https://raw.githubusercontent.com/da-h/AirLatex.vim/master/screenshot.png">
</p>


## First Use

This plugin is a bit paternalistic in its approach, since debugging multiple
login methods is not sustainable. See the [original AirLatex]() for a login
workflow.

### Authenticating
You should not have to reauthenticate once you have authenticated and leave the
session. Both of these methods are relatively persistent.

#### Go H$%^k yourself
To get started, login into your OverLeaf/ShareLatex instance in Firefox.
Firefox does not locally encrypt cookies, and AirLatex will [Cookie
Jack](https://owasp.org/www-community/attacks/Session_hijacking_attack) the
session cookie to connect to the server. It's a little like hacking yourself,
and a nice reminder that any program you are run on your machine can do this
and more. Here's [the relevant code]() if you are interested.

Once you are logged in, set `g:AirLatexCookieDB` to the path to the cookie database.
If you are lazy, just try:
```
let g:AirLatexCookieDB="~/.mozilla/firefox/*.default/cookies.sqlite"
```

For a custom or enterprise solution, you'll have to play with additional settings:
 - g:AirLatexCookieKey
 - g:AirLatexDomain

**You will need sqlite for this**

#### Set the cookie yourself
Log into to your instance, and take a look at your cookies.
You can explicitly set the Cookie with
```
let g:AirLatexCookie="cookies:overleaf2_session=justanexamplestring;maybe_morecookies=1"
```

For details on how to check your cookies [look at this issue]().

### Installing
#### With Nix
```
nix run github:dmadisetti/airlatex.vim#
```
Or add to your flake or what not. If you use nix, you know the drill.

### Normal Installation
1. Install the requirements. (python3)
    ```
    pip3 install tornado requests pynvim intervaltree beautifulsoup4
    ```
2. Install the Vim Plugin itself
    Using **Vim Plug**:
    ```
	  Plug 'dmadisetti/AirLatex.vim', {'do': ':UpdateRemotePlugins'}
    " Auth and settings mentioned in the documentation.
    ```
    
    Using **Vundle**:
    ```
	  Plugin 'dmadisetti/AirLatex.vim'
    " Auth and settings mentioned in the documentation.
    ```
    After installation using `:PluginInstall` run `:UpdateRemotePlugins` to register the python plugin.

### Launching
Open AirLatex in Vim with `:AirLatex`
Feel free to map AirLatex to a binding of your liking, e.g.:
   ```
   nmap <leader>a :AirLatex<CR>
   ```

## Settings

Variable | Possible Values | Description
-------- | --------------- | -----------
`g:AirLatexDomain` | `www.overleaf.com` (default) | Base url of the overleaf instance you would like to connect to.
`g:AirLatexShowArchived` | `0` (default, off), `1` (on) | Show/hide archived projects in the project list.
`g:AirLatexUseHTTPS` | `1` (default, on), `0` (off) | Choose between http/https.
`g:AirLatexLogLevel` | `NOTSET` (default), `DEBUG_GUI`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Verbosity of logging.
`g:AirLatexLogFile` | `AirLatex.log` (default)  | Log file name. (The file appears in the folder where vim has been started, but only if the log level is greater than `NOTSET`.)
`g:AirLatexWebsocketTimeout` | `10` (default)  | Number of seconds to wait before declaring the connection as *stale*. This may happen if the server does not answer a request by AirLatex. Setting to `"none"` disables this feature. However, it can be the case that you will not notice when something is wrong with the connection.
`g:AirLatexAllowInsecure` | `0` (default, off), `1` (on) | Allow insecure connection. For example, if the server is self hosted and/or the certificate is self-signed
`g:AirLatexTrackChanges` | `0` (default, off), `1` (on) | Allow track changes to be sent.

## Bindings

The Following bindings are scoped to the buffers. If you'd like to customize
them, please create a PR.

Buffer | Binding | Description
-------- | --------------- | -----------
sidebar | `q` | Close buffer
sidebar | `enter` | Enter project/ Toggle folder
sidebar | `d`, `D` | Leave project
document | visual `gv` | Mark section for drafting a comment
document | `R` | Refresh document, or bring back online if connection dropped.
document | command `:w` | If project is synced with github, create a new commit.
comments | `<C-n>` | Next comment (for stacked comments)
comments | `<C-p>` | Prev comment (for stacked comments)
comments | `ZZ` | Submit comment in draft
comments | `ZQ` | Quit Buffer/ discard draft
comments | (insert) | Start drafting a response if on thread
comments | `enter` | Un/resolve project if over the relevant option.


### Recommended Bindings

Additional bindings that are nice to have, but not required for functionality.

```vim
" AirLatex Keybinds
if exists("g:AirLatexIsActive") && g:AirLatexIsActive
  nnoremap <space>n :call AirLatex_NextCommentPosition()<CR>
  nnoremap <space>p :call AirLatex_PrevCommentPosition()<CR>
  nnoremap <F2> :call AirLatexToggleTracking()<CR>
  nnoremap <C-x> :call AirLatexToggle()<CR>
  nnoremap X :call AirLatexToggleComments()<CR>
endif
```

## Troubleshooting

**If you find a bug.**  
Feel free to open an issue!
To make things a bit easier for me, please use AirLatex' debug mode (`let g:AirLatexLogLevel='DEBUG'`).


## Credits

This plugin is a complete rework of [Vim-ShareLaTeX-Plugin](https://www.github.com/thomashn/Vim-ShareLaTeX-Plugin).  
I took all the good ideas and added even more vim love. ❥ ;)
