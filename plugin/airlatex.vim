
" check for requirements{{{
" ----------------------
if !has("nvim") && !has("python3")
   echoerr "AirLatex requires python to work."
   finish
endif
"}}}

" helpers {{{
" -------
let s:airlatex_home = expand('<sfile>:p:h:h')
let s:is_windows = has('win32') || has('win64') || has('win16') || has('dos32') || has('dos16')
if s:is_windows
    let s:fsep = ';'
    let s:psep = '\'
else
    let s:fsep = ':'
    let s:psep = '/'
endif
let s:pyfile = s:airlatex_home. s:psep. 'python'. s:psep. 'sidebar.py'
"}}}

let g:AirLatexArrowClosed="▸"
let g:AirLatexArrowOpen="▾"
let g:AirLatexWinPos="left"
let g:AirLatexWinSize=41


if !exists("g:AirLatexDomain")
    let g:AirLatexDomain="www.overleaf.com"
endif

if !exists("g:AirLatexCookieKey")
    let g:AirLatexCookieKey="overleaf_session2"
endif

if !exists("g:AirLatexLogLevel")
    let g:AirLatexLogLevel="NOTSET"
endif

if !exists("g:AirLatexLogFile")
    let g:AirLatexLogFile="AirLatex.log"
endif
autocmd BufNewFile,BufRead AirLatex.log set filetype=airlatex_log

if !exists("g:AirLatexUseHTTPS")
    let g:AirLatexUseHTTPS=1
endif

if !exists("g:AirLatexAllowInsecure")
    let g:AirLatexAllowInsecure=xor(g:AirLatexUseHTTPS, 1)
endif

if !exists("g:AirLatexShowArchived")
    let g:AirLatexShowArchived=0
endif

if !exists("g:AirLatexWebsocketTimeout")
    let g:AirLatexWebsocketTimeout=10
endif

if !exists("g:AirLatexTrackChanges")
    let g:AirLatexTrackChanges=0
endif

if !exists("g:AirLatexCookie") && exists("g:AirLatexCookieDB")
    let AirLatexSecret = trim(system(
    \   "sqlite3 'file:"
    \   . glob(g:AirLatexCookieDB)
    \   . "?immutable=1' 'select value from main.moz_cookies where name=\""
    \   . g:AirLatexCookieKey
    \   . "\" and host=\""
    \   . matchstr(g:AirLatexDomain, '\zs\..*')
    \   . "\";'"
    \))
    let g:AirLatexCookie = "cookies:" . g:AirLatexCookieKey . "=" . AirLatexSecret
endif

if exists('*airline#parts#define_function')
    function! AirLatexAirlineStatus()
      let var = 'g:AirLatexTrackChanges'
      if exists(var) && eval(var) == 1
        return ' (tracking)'
      else
        return ''
      endif
    endfunction
    function! AirLatexCheckOfflineBuffer()
      let buffer_name = expand('%:t')
      if buffer_name =~ 'Offline'
        return "Offline"
      else
        return ""
      endif
    endfunction
    " Define a new Airline part using the created function
    call airline#parts#define_function('air_latex', 'AirLatexAirlineStatus')
    call airline#parts#define_function('air_latex_error', 'AirLatexCheckOfflineBuffer')
    let g:airline_section_a = airline#section#create(['mode', 'air_latex'])
    let g:airline_section_error = airline#section#create(['air_latex_error'])
    call airline#update_statusline()
endif

" vim: set sw=4 sts=4 et fdm=marker:
