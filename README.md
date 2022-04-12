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
    pip3 install keyring tornado requests pynvim
    ```
2. Install the Vim Plugin itself
    Using **Vim Plug**:
    ```
	Plug 'da-h/AirLatex.vim', {'do': ':UpdateRemotePlugins'}
    " your login-name
    let g:AirLatexUsername="name@email.com"

    " optional: set server name
    let g:AirLatexDomain="www.overleaf.com"
    ```
    
    Using **Vundle**:
    ```
	Plugin 'da-h/AirLatex.vim'
    " your login-name
    let g:AirLatexUsername="name@email.com"

    " optional: set server name
    let g:AirLatexDomain="www.overleaf.com"
    ```
    After installation using `:PluginInstall` run `:UpdateRemotePlugins` to register the python plugin.
3. For the login, this plugin uses [keyring](https://pypi.org/project/keyring/) to store credentials by default.  
    On your first login, AirLatex will ask for your password. The credentials will be saved in your keyring. AirLatex does **not** manage credentials for security reasons.

    **If your overleaf/sharelatex instance uses a more complicated login process, set your username to "cookies"**.  
    In that case, AirLatex will ask you for the session cookies (that unfortunately needs to be lookuped-up by hand in your browser) and paste it into the promt.  
    Alternatively, assuming your session cookie is YOURSESSIONCOOKIE, you can circumvent the login prompt by setting the username to "cookies:YOURSESSIONCOOKIE".  
    **If you have any Idea how to improve this process, feel free to contribute or raise an issue**.
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
`g:AirLatexShowArchived` | `0` (default, off), `1` (on) | Show/hide archived projects in the project list.
`g:AirLatexUseHTTPS` | `1` (default, on), `0` (off) | Choose between http/https.
`g:AirLatexLogLevel` | `NOTSET` (default), `DEBUG_GUI`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Verbosity of logging.
`g:AirLatexLogFile` | `AirLatex.log` (default)  | Log file name. (The file appears in the folder where vim has been started, but only if the log level is greater than `NOTSET`.)
`g:AirLatexWebsocketTimeout` | `10` (default)  | Number of seconds to wait before declaring the connection as *stale*. This may happen if the server does not answer a request by AirLatex. Setting to `"none"` disables this feature. However, it can be the case that you will not notice when something is wrong with the connection.
`g:AirLatex_insecure` | `0` (default, off), `1` (on) | Allow insecure connection. For example, if the server is self hosted and/or the certificate is self-signed


Troubleshooting
===============
**If you find a bug.**  
Feel free to open an issue!
To make things a bit easier for me, please use AirLatex' debug mode (`leg g:AirLatexLogLevel='DEBUG'`).


Credits
=======
This plugin is a complete rework of [Vim-ShareLaTeX-Plugin](https://www.github.com/thomashn/Vim-ShareLaTeX-Plugin).  
I took all the good ideas and added even more vim love. ❥ ;)
