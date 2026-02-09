_mimic3_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="-h --help --remote --stdin-format --voice -v --speaker -s --voices-dir --voices --output-dir --output-naming --id-delimiter --interactive --csv --csv-delimiter --csv-voice --mark-file --noise-scale --length-scale --noise-w --result-queue-size --process-on-blank-line --ssml --stdout --preload-voice --play-program --cuda --deterministic --seed --version --debug"

    d='/home/k/.local/share/mycroft/mimic3/voices/'
    case "$prev" in
        --voice|-m)
            pushd "$d" > /dev/null
            COMPREPLY=( $(compgen -f -X '!*' -- "$cur") $(compgen -d -- "$cur") )
            popd > /dev/null
            return 0
            ;;
        --speaker)
            pushd "$d"
            p="${COMP_WORDS[COMP_CWORD-2]}"
            COMPREPLY=( $(compgen -f -X '!*' -- "$cur") $(g "$cur" "${p}/speakers.txt") )
            popd
            return 0
            ;;
        *)
            COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
            return 0
            ;;
    esac
}

complete -F _mimic3_completions mimic3
