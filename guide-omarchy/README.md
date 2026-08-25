# Guide Omarchy — sources

Ce dossier contient le guide PDF et tout ce qu'il faut pour le régénérer.

```
guide-omarchy-fr.pdf   le livrable — 138 pages, A4
build.py               le script de génération
src/guide.html         le contenu du guide (un seul fichier)
src/guide.css          la feuille de style d'impression
src/images/            les captures d'écran, téléchargées depuis omarchy.org/manual/images/
```

## Régénérer le PDF

```bash
pip install playwright pypdf
python3 build.py
```

Chromium est nécessaire. `build.py` utilise celui que Playwright a installé ; si la
version épinglée par Playwright n'est pas celle qui est présente, il retombe
automatiquement sur `/opt/pw-browsers/chromium` ou sur le `chromium-*` le plus récent
trouvé à cet emplacement (voir `chromium_path()`).

Le script fait trois passes :

1. rendu HTML → PDF, sommaire sans numéros de page ;
2. relevé de la page de chaque chapitre dans le PDF produit (recherche du marqueur
   « CHAPITRE n » dans le texte extrait), réinjection dans le sommaire, second rendu ;
3. ajout des signets PDF avec `pypdf`.

Le sommaire et les signets sont construits **à partir du document** : chaque
`<div class="part">` et chaque `<section class="chapter">` y entre automatiquement.
Il n'y a donc rien à tenir à jour à la main en ajoutant un chapitre.

Le script signale sur la sortie d'erreur toute image cassée et tout chapitre qu'il n'a
pas su localiser dans le PDF, et sort avec un code non nul dans ce cas.

## Conventions du HTML

- **Une partie :** `<div class="part">` avec `.kicker` (« Partie III ») et
  `<h1 class="part-title">`.
- **Un chapitre :** `<section class="chapter">` avec
  `<h2><span class="chapno">Chapitre 12</span>Titre</h2>` puis `<p class="chapeau">`.
  Le libellé `Chapitre n` / `Annexe X` sert de marqueur pour la pagination : il doit
  être unique.
- **Encadrés :** `<div class="box">` (astuce), `.box.warn` (attention),
  `.box.danger` (avertissement fort), `.box.more` (pour aller plus loin), chacun
  ouvert par `<span class="label">`.
- **Sources :** chaque chapitre se termine par `<div class="src">` listant les pages
  du manuel officiel dont il découle.
- Les marges d'impression sont dans la règle `@page` de `guide.css`, **pas** dans
  l'appel à `page.pdf()` : une règle `@page` l'emporte sur le paramètre `margin` de
  l'API.

## Les images

Elles proviennent de `https://omarchy.org/manual/images/`. Elles ont été réduites
(1200 px de large, 850 px pour les aperçus de thèmes) et converties en JPEG : Chromium
réencode les WebP sans perte à l'impression, ce qui faisait passer le PDF de 3,4 Mo à
plus de 11 Mo.

## Mettre le guide à jour

Omarchy est une distribution *rolling release* et son manuel évolue. Pour une nouvelle
version majeure : recouper les chapitres concernés avec omarchy.org/manual, corriger
`src/guide.html`, mettre à jour le numéro de version sur la couverture et en annexe D,
puis relancer `build.py`.
