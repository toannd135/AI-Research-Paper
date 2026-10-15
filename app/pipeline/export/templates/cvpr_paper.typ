// Academic Two-Column Paper Template for Typst (IEEE / CVPR style)
// Designed for AI Research Paper Generator

#let cvpr_paper(
  title: "Untitled Research Paper",
  authors: (),
  affiliations: (),
  abstract: none,
  keywords: (),
  body
) = {
  // Page setup
  set page(
    paper: "a4",
    margin: (x: 1.8cm, top: 2.2cm, bottom: 2.2cm),
    header: context {
      if here().page() > 1 {
        align(center)[
          #text(size: 8pt, fill: luma(100), font: "Times New Roman")[
            #title
          ]
        ]
      }
    },
    footer: context {
      align(center)[
        #text(size: 9pt, font: "Times New Roman")[
          #counter(page).display()
        ]
      ]
    }
  )

  // Typography settings
  set text(
    font: ("Times New Roman", "DejaVu Serif", "Noto Serif", "serif"),
    size: 10pt,
    lang: "en",
    hyphenate: true
  )

  set par(
    justify: true,
    leading: 0.58em,
    first-line-indent: 1.2em
  )

  // Math equations setup
  set math.equation(numbering: "(1)")
  show math.equation.where(block: true): it => {
    v(0.4em)
    it
    v(0.4em)
  }

  // Headings styling
  show heading.where(level: 1): it => {
    set text(size: 11pt, weight: "bold")
    v(1em, weak: true)
    it
    v(0.5em, weak: true)
  }

  show heading.where(level: 2): it => {
    set text(size: 10pt, weight: "bold")
    v(0.8em, weak: true)
    it
    v(0.4em, weak: true)
  }

  show heading.where(level: 3): it => {
    set text(size: 10pt, style: "italic", weight: "bold")
    v(0.6em, weak: true)
    it
    v(0.3em, weak: true)
  }

  // Figures and Tables styling
  show figure.where(kind: table): set figure.caption(position: top)
  show figure.caption: it => [
    #text(size: 8.5pt, font: ("Arial", "Helvetica", "Noto Sans", "sans-serif"))[
      #it
    ]
  ]

  // --- FRONT MATTER (Full-width Single Column) ---
  align(center)[
    // Title
    #v(0.5cm)
    #text(size: 17pt, weight: "bold")[#title]
    #v(0.8em)

    // Authors & Affiliations
    #if authors.len() > 0 [
      #text(size: 11pt, weight: "bold")[
        #authors.join("    ")
      ]
      #v(0.3em)
    ]

    #if affiliations.len() > 0 [
      #text(size: 9.5pt, style: "italic", fill: luma(80))[
        #affiliations.join("\n")
      ]
      #v(1em)
    ]
  ]

  // Abstract & Keywords block
  if abstract != none [
    #align(center)[
      #block(width: 88%)[
        #line(length: 100%, stroke: 0.8pt)
        #v(0.4em)
        #align(center)[#text(size: 10pt, weight: "bold")[Abstract]]
        #v(0.2em)
        #align(left)[
          #set par(justify: true, first-line-indent: 0pt)
          #text(size: 9pt)[#abstract]
        ]
        #if keywords.len() > 0 [
          #v(0.4em)
          #align(left)[
            #set par(first-line-indent: 0pt)
            #text(size: 9pt)[*Keywords:* #keywords.join(", ")]
          ]
        ]
        #v(0.4em)
        #line(length: 100%, stroke: 0.8pt)
        #v(1.2em)
      ]
    ]
  ]

  // --- MAIN BODY (Academic Two Columns) ---
  columns(2, gutter: 18pt)[
    #body
  ]
}
