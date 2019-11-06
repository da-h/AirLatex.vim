
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
let g:AirLatexWinSize=31

function! AirLatex()
	let g:cmd="start"
    execute 'py3file' s:pyfile
endfunction

function AirLatex_project_update()
	let g:cmd="update"
    execute 'py3file' s:pyfile
endfunction

function AirLatex_project_enter()
	let g:cmd="enter"
    execute 'py3file' s:pyfile
endfunction

function AirLatex_update_pos()
	let g:cmd="updatePos"
    execute 'py3file' s:pyfile
endfunction

function AirLatex_close()
	let g:cmd="close"
    execute 'py3file' s:pyfile
endfunction

function AirLatex_writeBuffer()
	let g:cmd="writeBuffer"
    execute 'py3file' s:pyfile
endfunction


nmap <leader>a :call AirLatex()<cr>

" globals
if !exists("g:airlatex_domain")
    let g:airlatex_domain="www.sharelatex.com"
endif

" vim: set sw=4 sts=4 et fdm=marker:
