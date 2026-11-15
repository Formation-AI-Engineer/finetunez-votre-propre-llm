# Fonctions communes aux étapes Kaggle, à charger avec `source scripts/kaggle/common.sh`.

PY=(uv run --frozen --no-dev python)

# Copie les résultats dans /kaggle/working, le seul dossier conservé avec la version du notebook.
# Seuls outputs/eval et outputs/logs y vont : jamais le code, ni .git, ni les jetons.
save_outputs() {
    if [ -d /kaggle/working ]; then
        for dir in "$@"; do
            [ -d "$dir" ] && mkdir -p "/kaggle/working/$dir" && cp -r "$dir/." "/kaggle/working/$dir/"
        done
        echo "Résultats copiés dans /kaggle/working : $*"
    fi
}

# Attend un processus lancé en arrière-plan ; en cas d'échec, affiche la fin de son journal.
wait_for() {
    local pid=$1 log=$2
    if wait "$pid"; then
        return 0
    fi
    echo "ÉCHEC, fin de $log :"
    tail -n 40 "$log"
    return 1
}
