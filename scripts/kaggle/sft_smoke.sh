#!/usr/bin/env bash
# Étape « sft_smoke » : contrôles rapides du script SFT avant le run complet (environ 15 minutes).
#
# cuda:0 — sur-apprentissage volontaire : 100 exemples, 15 époques, sans validation. La perte doit
#          chuter vers 0 ; sinon la perte, le masque ou le taux d'apprentissage sont faux. Puis
#          20 questions par tâche avec cet adaptateur : les réponses doivent se terminer par
#          <|im_end|> (peu de réponses coupées) et suivre le format appris. Sans l'entraînement
#          des lignes de <|im_end|> (lora.trainable_tokens), elles étaient toutes coupées.
# cuda:1 — reprise : run de 40 pas interrompu (kill) juste après le checkpoint du pas 20, puis
#          relancé avec --resume. Il doit repartir du pas 20 et finir au pas 40.
set -uo pipefail
source scripts/kaggle/common.sh

mkdir -p outputs/logs
# Le clone survit d'un lancement à l'autre dans une session Kaggle : sans ce nettoyage, un run
# qui plante laisserait afficher les résultats du lancement précédent.
rm -rf outputs/sft/smoke-overfit outputs/sft/smoke-resume outputs/eval/smoke-overfit

overfit() {
    CUDA_VISIBLE_DEVICES=0 "${PY[@]}" scripts/train_sft.py --name smoke-overfit --limit 100 \
        --set training.num_train_epochs=15 --set training.eval_strategy=no \
        --set training.lr_scheduler_type=constant --set training.warmup_steps=0 &&
        "${PY[@]}" scripts/evaluate.py --name smoke-overfit \
            --adapter outputs/sft/smoke-overfit/best --limit 20 --device cuda:0
}

resume() {
    local dir=outputs/sft/smoke-resume
    local args=(scripts/train_sft.py --name smoke-resume --set training.max_steps=40
        --set training.eval_steps=20)
    rm -rf "$dir"
    CUDA_VISIBLE_DEVICES=1 "${PY[@]}" "${args[@]}" &
    local pid=$!
    # trainer_state.json est écrit en dernier dans un checkpoint : le checkpoint est complet.
    until [ -f "$dir/checkpoint-20/trainer_state.json" ] || ! kill -0 "$pid" 2>/dev/null; do
        sleep 5
    done
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Le run s'est arrêté avant le checkpoint du pas 20."
        return 1
    fi
    sleep 5
    # Le processus Python lui-même, pas seulement `uv run` : deux runs écriraient au même endroit.
    pkill -TERM -f -- "train_sft.py --name smoke-resume"
    wait "$pid" 2>/dev/null
    while pgrep -f -- "train_sft.py --name smoke-resume" >/dev/null; do sleep 2; done
    echo "Interrompu après le checkpoint 20 ; reprise."
    CUDA_VISIBLE_DEVICES=1 "${PY[@]}" "${args[@]}" --resume
}

overfit > outputs/logs/sft_smoke_overfit.log 2>&1 &
overfit_pid=$!
resume > outputs/logs/sft_smoke_resume.log 2>&1 &
resume_pid=$!

status=0
wait_for "$overfit_pid" outputs/logs/sft_smoke_overfit.log || status=1
wait_for "$resume_pid" outputs/logs/sft_smoke_resume.log || status=1

# Seuls les journaux et les résumés sont gardés : les adaptateurs de ces essais ne servent plus.
save_outputs outputs/eval outputs/logs
for run in smoke-overfit smoke-resume; do
    if [ -f "outputs/sft/$run/run.json" ]; then
        mkdir -p "/kaggle/working/outputs/sft/$run" 2>/dev/null &&
            cp "outputs/sft/$run/run.json" "/kaggle/working/outputs/sft/$run/" 2>/dev/null
    fi
done

echo "==== Sur-apprentissage (cuda:0)"
grep -E "^---- contrôles|trainable params|exemples d'entraînement" outputs/logs/sft_smoke_overfit.log
"${PY[@]}" - <<'EOF'
import json
from pathlib import Path

run = Path("outputs/sft/smoke-overfit/run.json")
if run.exists():
    r = json.loads(run.read_text())
    print(f"perte : {r['first_train_loss']:.3f} -> {r['last_train_loss']:.3f} en {r['steps']} pas, "
          f"{r['minutes']} min, {r['peak_gpu_memory_gib']} Gio")
EOF
[ -f outputs/eval/smoke-overfit/validation/summary.md ] &&
    sed -n '1,/^## Exemples/p' outputs/eval/smoke-overfit/validation/summary.md

echo "==== Reprise (cuda:1)"
grep -E "^Reprise|Interrompu|s'est arrêté" outputs/logs/sft_smoke_resume.log
"${PY[@]}" - <<'EOF'
import json
from pathlib import Path

run = Path("outputs/sft/smoke-resume/run.json")
if run.exists():
    r = json.loads(run.read_text())
    ok = r["resumed_from"] and r["resumed_from"].endswith("checkpoint-20") and r["steps"] == 40
    print(f"repris de {r['resumed_from']}, fini au pas {r['steps']}, pertes de validation "
          f"{[round(x, 3) for x in r['eval_losses']]} : {'OK' if ok else 'ÉCHEC'}")
    print(f"débit : {r['train_metrics'].get('train_samples_per_second')} exemples/s, "
          f"{r['peak_gpu_memory_gib']} Gio")
EOF
exit "$status"
