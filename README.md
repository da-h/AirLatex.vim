AirLatex.vim
============
**Current State**: Work in Progress  
(Please use it right now only for testing purposes.)

<p align="center">
  <img src="https://raw.githubusercontent.com/da-h/AirLatex.vim/master/screenshot.png">
</p>

Features
========
**That's possible already**:
- open documents and **write remotely**
- **cursor positions** are sent to the server
- list all projects
- custom servers

**Not implemented, yet**:  
This project is just at its dawn, however I plan to also implement the following features in the future:
- show colored **cursor positions of other users**
- send **recompile**-command to the server
- **file operations** inside vim (new file/copy/delete)
- **review mode** (comments, track changes, ...)



Installation / First Use
========================
**Notes regarding Vim 8 support**: Vim 8 will be supported in the future, however i could not make it work completely, yet. If you need this feature feel free to contribute. (See `vim8` branch for current state.) ;)

1. Install the requirements. (python3)
    ```
    pip3 install browser_cookie3 tornado requests pynvim
    ```
2. Install the Vim Plugin itself
    Using **Vim Plug**:
    ```
	Plug 'da-h/AirLatex.vim', {'do': ':UpdateRemotePlugins'}

    " optional: set server name
    let g:AirLatexDomain="www.overleaf.com"
    ```
    
    Using **Vundle**:
    ```
	Plugin 'da-h/AirLatex.vim'

    " optional: set server name
    let g:AirLatexDomain="www.overleaf.com"
    ```
    After installation using `:PluginInstall` run `:UpdateRemotePlugins` to register the python plugin.
3. For the login, this plugin uses [browser_cookie3](https://github.com/borisbabic/browser_cookie3).  
So .... simply log in to your sharelatex/overleaf instance using your browser.  
**Note**: **I recommend to use Firefox for the login process.** See below how to specify the browser to use for login. If you use Firefox, browser_cookie3 should find the right cookie for the server automatically. :)  
Even though, Chrome should be possible, I found it harder to configure on my system. (Please check the project page of browser_cookie3 if you need to use Chrome).
4. Open AirLatex in Vim with `:AirLatex`
Feel free to map AirLatex to a binding of your liking, e.g.:
   ```
   nmap <leader>a :AirLatex<CR>
   ```

Settings
========

Variable | Possible Values | Description
-------- | --------------- | -----------
`g:AirLatexDomain` | `www.overleaf.com` (default) | Base url of the overleaf instance you would like to connect to.
`g:AirLatexCookieBrowser` | `auto` (default), `firefox`, `chromium` | Browser to look for session cookies. (The option `auto` queries the cookies from all known Browsers on your system.)
`g:AirLatexShowArchived` | `0` (default, off), `1` (on) | Show/hide archived projects in the project list.
`g:AirLatexUseHTTPS` | `1` (default, on), `0` (off) | Choose between http/https.
`g:AirLatexLogLevel` | `NOTSET` (default), `DEBUG_GUI`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Verbosity of logging.
`g:AirLatexLogFile` | `AirLatex.log` (default)  | Log file name. (The file appears in the folder where vim has been started, but only if the log level is greater than `NOTSET`.)


Troubleshooting
===============
**Cannot login / Offline / Unauthorized.**  
The most common solution is: “Did you turn it on and off again“. Not kidding. **Reload the project page without using the browser cache** to reset the cookies.  
(Typically you can hit Ctrl + Shift + R to reload the page without using the cache, or clear the cookie cache, e.g. by clicking on the little lock beside the page URL.)

More details / Debugging:
The most common problem with this kind of problem is that the session cookies cannot be found by [browser_cookie3](https://github.com/borisbabic/browser_cookie3). If you use AirLatex' debug mode (`leg g:AirLatexLogLevel='DEBUG'`), the Log file will list all cookies that have been found. In all settings that I've tried, at least one cookie, `overleaf_session2`, is required to at least make the login work. More prominent instances (i.e. www.overleaf.com) may also require the cookie `gke-route` to be recognized. (Just check your Browser which cookies are actually needed for the login).

**If you find a bug.**  
Feel free to open an issue!


Credits
=======
This plugin is a complete rework of [Vim-ShareLaTeX-Plugin](https://www.github.com/thomashn/Vim-ShareLaTeX-Plugin).  
I took all the good ideas and added even more vim love. ❥ ;)
