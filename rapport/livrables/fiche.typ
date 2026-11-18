// Mise en page commune des fiches de livrables (même charte que le rapport).
#let accent = rgb("#1f4e79")
#let muted = rgb("#5a6270")
#let soft = rgb("#eef2f7")

#let fiche(numero: "", titre: "", sous-titre: "", body) = {
  set document(title: "Livrable " + numero + " : " + titre)
  set page(paper: "a4", margin: (x: 2.1cm, top: 2cm, bottom: 2cm), numbering: "1 / 1",
    number-align: right,
    header: context {
      set text(8pt, fill: muted)
      [POC d'agent de triage médical — CHSA #h(1fr) Livrable #numero · Lamine CAMARA]
    })
  set text(font: "Libertinus Serif", size: 10.5pt, lang: "fr")
  set par(justify: true, leading: 0.58em, spacing: 0.9em)
  show heading.where(level: 2): it => block(above: 1.1em, below: 0.6em, text(12pt, fill: accent, weight: "bold", it))
  show raw: set text(font: "DejaVu Sans Mono", size: 8.5pt)
  show raw.where(block: true): it => block(fill: soft, inset: 8pt, radius: 3pt, width: 100%, it)
  set table(
    stroke: (x, y) => (top: if y <= 1 { 0.6pt + accent } else { 0.3pt + luma(200) }),
    inset: (x: 5pt, y: 3.5pt), align: left,
    fill: (x, y) => if y == 0 { soft },
  )
  show table: set text(9pt)
  show table: set par(justify: false)
  show table.cell.where(y: 0): set text(weight: "bold")

  block(below: 0.4em, text(10pt, fill: muted)[Livrable n° #numero · Centre Hospitalier Saint-Aurélien])
  block(below: 0.3em, text(20pt, weight: "bold", fill: accent, titre))
  if sous-titre != "" { block(below: 0.8em, text(11.5pt, sous-titre)) }
  line(length: 100%, stroke: 0.6pt + accent)
  body
}

// Encadré d'accès ou d'avertissement.
#let note(body) = block(fill: soft, inset: 8pt, radius: 3pt, width: 100%, text(9.5pt, body))
