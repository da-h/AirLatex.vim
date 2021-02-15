syn clear
syntax match ALLogLine #^.*$# contains=ALLogFile,ALLogFunc,ALLogLineNo,ALLogMsg
" syntax match ALLogMsg /.*$/ contained containedin=ALLogLine
syntax match ALLogFile #^[^/]*# contained containedin=ALLogLine
syntax match ALLogFunc #\v/\zs[^:]*\ze\s\## contained containedin=ALLogLine
syntax match ALLogLineNo #\zs\#\d\+\ze\s*:# contained containedin=ALLogLine

hi def link ALLogFile Special
hi def link ALLogFunc Function
" hi def link ALLogMsg Normal
hi def link ALLogLineNo Comment
