# Analyse: Hvad vi kan tage fra `scroll-film-studio` til Qleer-sider

**Formål:** Skillet `scroll-film-studio` bygger hele hjemmesider hvor siden er én lang
cinematisk indstilling der scrubber på scroll. Det er *ikke* det vi skal bruge. Men
processen, lovene og Higgsfield-pipelinen indeni er stærke — og de kan destilleres til
noget der gør vores **page-produktion** (vandtestside, advertorial, nye sidetyper) markant
bedre.

Dette dokument er en analyse og en anbefaling. Intet er implementeret.

---

## 0. Den centrale forskel man skal holde fast i

| | scroll-film-studio | Qleer-sider |
|---|---|---|
| Output | Et helt website | **Én side ad gangen** |
| Succeskriterie | Wow, "hvordan har de lavet det" | **Konvertering fra betalt trafik** |
| Brand | Nyt univers per build | **Ét brand, mange sider** |
| Vægt-budget | Ubegrænset (300 frames ≈ 20-40 MB) | **Mobil på 4G, LCP < 2,5s** |
| Sandheden er | Filmen ("siden er en afspiller") | **Argumentet og tilbuddet** |

Alt herunder er filtreret gennem den tabel. Når en mekanik fra skillet kun tjener æstetik,
ryger den ud. Når den tjener *klarhed, tempo eller troværdighed*, tager vi den.

---

## 1. Det største enkeltstående tyveri: **koncept-pitchet før byg** (STEP 1)

Skillet bygger aldrig noget før det har pitchet **2-3 navngivne koncepter** med en konkret
gennemgang af hvad man rent faktisk *ser* — ikke en tese, men en scroll-fortælling:

> *"Du åbner på en måneskinsmark, kæmpe serif-wordmark der svæver. Scroll: kameraet dykker
> ind i én blomst… kronbladene åbner sig… du falder gennem gyldne gløder…"*

Ét koncept markeres eksplicit **"(Anbefalet)"**, og brugeren kan sige "du vælger".

**Hvorfor det er guld for os:** vores `gpp-builder` går direkte fra intake-tabel til at
bygge 20+ sektioner Liquid. Hvis vinklen er forkert, opdager vi det efter 2.000 linjer kode.
Et pitch koster 30 sekunder og fanger det før.

**Oversat til Qleer** — for vandtestsiden ville det se sådan ud:

- **"Rapporten"** *(Anbefalet)* — siden er formet som en laboratorierapport om læserens eget
  vand. Åbner med et testresultat-kort med deres postnummer. Scroll: hvad tallene betyder →
  hvad de andre ikke tester for → mekanismen → produktet som svaret.
- **"Det du ikke kan se"** — visuelt drevet. Åbner på et glas rent vand i makro, scroll
  zoomer indtil man ser hvad der faktisk er i det. Hårdere hook, tungere på billeder.
- **"Blindtesten"** — social proof-først. 200 husstande testede uden at vide hvad de fik.

Samme produkt, samme tilbud, tre helt forskellige sider. **Det valg skal træffes før
byggeriet, ikke undervejs.**

---

## 2. Interviewet med "du bestemmer"-udgang (STEP 0)

Skillets interview har en regel der er værd at kopiere ordret:

> *Hvert kreativt spørgsmål har en "du bestemmer"-vej. Blokér aldrig på et designsvar du selv
> kan give godt.*

Vores intake-tabel i `gpp-builder` er ren faktaindsamling (persona, pris, batteri, offer).
Det er rigtigt og skal blive. Men der mangler ét spørgsmål fra skillet, oversat:

> **"Rejsen — hvor starter læseren, og hvor ender de?"** Ikke sektionsrækkefølgen, men
> *transformationen*: fra "jeg tænker ikke over mit vand" til "jeg kan ikke leve med det her".

Det er dét spørgsmål der gør forskellen på en side der lister argumenter og en side der
fortæller noget. Det er også det eneste sted skillets "one continuous shot"-tankegang
faktisk giver mening hos os: **ikke ét kamera, men ét ubrudt argument.**

---

## 3. Den gyldne regel + delegationsmodellen — tages næsten ordret

Skillet er meget skarpt på hvad der må uddelegeres:

| Arbejde | Hvem | Vores oversættelse |
|---|---|---|
| Koncept, copy, sektionsdesign, Liquid, endeligt review | **Claude — aldrig uddelegeret** | Uændret |
| Første udkast: ét afsnit, ét FAQ-sæt, én testimonial-blok | **Subagents — og du omskriver hvert udkast; intet fra en subagent shipper uredigeret** | Uændret. Det er den vigtigste sætning i hele skillet |
| Billed-/videogenerering | (Higgsfield) | **Higgsfield MCP** |
| Screenshots, vægt-måling, upload, verifikation | **Ren kode, ingen model** | Puppeteer + Shopify GraphQL |

"Second-model sparring" (at spørge en anden frontier-model om at angribe pitchet) — dropper
vi. Lav værdi på en konverteringsside, og det tilføjer afhængigheder.

---

## 4. Verifikations-harnesset — det største hul i vores nuværende workflow

Det her er den del vi mangler mest, og skillet har den bedste formulering af hvorfor:

> **"Bed aldrig brugeren om at kigge efter noget du kan bevise."**

Skillets kontrakt er tre ting:
1. `?jump=<scrollY>` → siden lander præ-scrollet med al scroll-state tvunget på plads
2. `window.__ready = true` → fyrer først når siden faktisk er klar
3. `verify.js` → puppeteer + system-Chrome, screenshot ved enhver position + jank-test

Og en vigtig teknisk pointe: **preview-paneler throttler skjulte faner** (rAF fryser →
forældede screenshots). Derfor eksisterer harnesset overhovedet.

**Oversat til Qleer:** vi uploader til draft-theme og … kigger. I stedet:

- Screenshot af preview-URL'en ved hver sektion, **mobil først (390×844)** — det er dér den
  betalte trafik er — derefter desktop.
- Erstat jank-testen med en **vægt- og LCP-gate**: total sidevægt, LCP, CLS. En GPP der
  vejer 6 MB er en dyrere fejl end en der hakker.
- Faste tjek der kan bevises frem for vurderes: er CTA over folden på mobil? Renderer
  prisblokken? Fyrer popup ved 55%? Åbner FAQ-accordion? Er der vandret overflow?

Det er ~80 linjer Node og fjerner hele "kan du lige tjekke om den ser rigtig ud"-runden.

---

## 5. Motion-ordforrådet — tag udvalgt, smid resten

`engine.md` har et helt bibliotek af scroll-motion. Vores `gpp-builder` har præcis **én**
primitiv: `.pl-reveal` fade-up via IntersectionObserver. Det er tyndt. Herfra tager vi:

**Tag med:**
- **Char-split headline-reveal** på hero — wordmark/headline splittes i spans, staggered
  `yPercent:120 → 0` med `power4.out`. Kører én gang, ikke scroll-afhængig. Premium-følelse
  for ~0 kb.
- **Clip-path reveal** (`inset(0 0 100% 0) → inset(0)`) til editorial-rækker — perfekt til
  før/efter og rapport-sektionen.
- **Tællere** med `snap: { textContent: 1 }` og `once: true` — vores kategori-stat-sektion
  (§9, stort tal + søjlediagram) er statisk i dag. Et tal der tæller op er billigere end
  et diagram og læses hurtigere.
- **Én — og kun én — pinned scrubbed scene per side**, og kun hvor transformationen *er*
  argumentet (fx "hvad sker der faktisk i vandet"). Aldrig som dekoration.
- **Ordre-loven, ordret:** ScrollTriggers refreshes i oprettelsesrækkefølge — opret alle
  pinned scener **først**, ambient/baggrund **bagefter**. Ellers beregnes positioner før
  pin-spacers findes, og alt efter pinnen sidder tusindvis af pixels forkert. Stille fejl.
- **`prefers-reduced-motion`** i hvert build. Mangler helt hos os i dag.

**Smid væk:**
- Velocity-skew, marquee-drift, horisontale pinned runs — dekorativ støj på en side der
  skal sælge.
- **Lenis smooth-scroll** — flag som risikabelt. Det kaprer scroll og opfører sig
  uforudsigeligt i Meta/TikTok in-app-browsere, som er præcis dér vores trafik kommer fra.
  Skillet gør det til standard; vi bør ikke.

---

## 6. Sømme og sticky header — to mekanikker der generaliserer godt

**Sømløs overgang (film → indhold):** skillet sampler den sidste frames bundfarve og starter
næste sektions baggrund på præcis den hex, plus en bundfade der ramper ind over de sidste 8%.

Generaliseret til os: vores sider veksler mørk/lys i bånd (hero mørk → trust lys → citat mørk
→ produkt lys). I dag er de bare stablet. **Overgangs-disciplin** — en gradient-landingszone
der smelter mørk → brand-lys i stedet for en hård kant — er forskellen på "designet" og
"sammensat af sektioner". Gratis at indføre, ren CSS.

**Adaptiv header:** skillet sampler frame-luminans hver ~180 ms og skifter en `.on-light`-klasse,
hvor alle header-farver kører gennem `currentColor` så én klasse vender det hele.

Vi behøver ikke canvas-sampling — vores baggrunde er kendte. Men *mønstret* er rigtigt for
vores sticky topbar over en mørk hero: én `.on-light`-klasse skiftet af en IntersectionObserver
på hero-sektionen, alle farver via `currentColor`. Løser at topbaren i dag er hvid uanset hvad
der er bag den.

---

## 7. Higgsfield — her ligger den store gevinst, men den skal vendes om

Det er her skillet er mest værdifuldt for os, og samtidig mest misforstået hvis man tager det
bogstaveligt. I skillet producerer Higgsfield en 5-kapitels sammenhængende **video** → 300
frames → canvas-scrubber. **Det output er forkert for os.** Men pipelinen bagved er rigtig.

### 7.1 Stills som asset-fabrik, ikke video
Higgsfields billedgenerering bliver kilden til det vi i dag enten mangler eller
håndtegner: hero-billeder, den emotionelle rejse-strip (i dag bamse-SVG'er), biologi-kortenes
ikoner, før/efter-visuals, produkt-i-kontekst, portrætter til testimonials. **En asset-fabrik
per side** er langt mere værd for Qleer end en scroll-film nogensinde bliver.

### 7.2 Kædeloven overlever — men med nyt formål
Skillets lov er: hvert klips `--start-image` er den *bogstavelige* sidste frame af det
forrige — ikke et lookalike-keyframe, de faktiske pixels. Formålet dér er
video-kontinuitet.

**Oversat til os:** generér hero-billedet først, og brug det derefter som start-/referencebillede
for **alle andre billeder på siden**. Så ser hele siden ud som ét fotoshoot i stedet for otte
stock-billeder. Det er skillets *"ét univers per brand"*-lov korrekt oversat til vores
virkelighed: **ét univers per side** — brandet er konstant, det visuelle motiv varierer per
sidetype (vandtestsiden = lab/rapport, advertorial = redaktionelt/presse).

### 7.3 SSIM-porten → en brand-konsistens-port
Man kan ikke SSIM'e to forskellige motiver. Men princippet — **mål, kig ikke** — oversættes:
sample hvert genereret assets palette og luminans og tjek at det ligger inden for
design-systemets tokens (`#111318`, `#C4956A`, `#F8F7F5`, `#F0E8DC`). Off-brand assets
afvises og genereres igen *før* de ryger i Liquid'en, ikke efter at nogen har set siden.

### 7.4 Hvis der overhovedet skal video på
Ét enkelt 3-5s loop, muted, autoplay, med poster-frame og lazy loading — i hero eller i
mekanisme-sektionen. **Ikke** en 300-frames scrubber. Vægt-budgettet afgør det, ikke smagen.

### 7.5 Omkostningsdisciplinen tages 1:1
Skillets fire regler holder uændret hos os:
1. **Audio OFF** (`--generate-audio false`) — audio ~3-dobler regningen i stilhed.
2. **Bekræft før forbrug** — oplys totalen før generering, vis kvitteringen efter.
3. **Draft billigt, master én gang** — validér hele kæden på laveste tier, kør kun godkendte
   prompts i fuld opløsning.
4. **Genbrug materialet** — og her har vi en bonus skillet ikke har: ét asset-sæt kan drive
   **vandtestsiden, advertorialen og annoncerne**. Materialet er omkostningen; genbrug er gratis.

Plus den praktiske: **~15% af Higgsfield-jobs fejler server-side uden grund og bliver ikke
faktureret — prøv bare igen.** Værd at have skrevet ned, ellers fejlsøger man noget der ikke er i stykker.

---

## 8. Hvad vi eksplicit skal droppe

- **"Hele siden er ét shot"** — præmissen. 850vh scroll-drivere hører ikke hjemme på en
  konverteringsside.
- **Canvas frame-scrubberen** (300 JPEGs, ImageBitmap sliding window, DPR-cap, lerped
  playhead). Teknisk imponerende, 20-40 MB. Dødsdom for Meta-trafik på mobil.
- **Nye fonte og palet per build.** Skillet siger "aldrig to brands der ligner hinanden" —
  hos os er det modsatte sandt: Raleway og KLEEN-tokens er konstanten. Variationen ligger i
  motiv og sektionsarkitektur, ikke i typografi.
- **Vercel-deploy** — vi shipper til Shopify draft-theme.
- **"Footage-first"-loven** ("filmen er sandheden, siden er en afspiller") — vendes om:
  **tilbuddet og argumentet er sandheden; billederne tjener dem.**

---

## 9. Anbefaling

Byg ikke et nyt skill ved siden af. **Opgradér `gpp-builder`** med fire ting — i denne
prioritetsrækkefølge:

1. **Koncept-pitch som nyt trin mellem intake og byg** (§1). Størst effekt, mindst arbejde.
2. **Verifikations-harness** — `?jump` + `__ready` + screenshot- og vægt-gate (§4). Fjerner
   den manuelle QA-runde helt.
3. **Ny reference: `motion.md`** — det udvalgte motion-ordforråd, ordre-loven,
   `prefers-reduced-motion`, overgangs-disciplin og adaptiv topbar (§5-6).
4. **Ny reference: `asset-pipeline.md`** — Higgsfield som asset-fabrik: hero-først-kæden,
   brand-konsistens-porten, omkostningsdisciplinen (§7).

Punkt 1 og 2 kan stå alene og giver værdi fra første side. Punkt 3 og 4 er dér den visuelle
kvalitet reelt løftes.

---

## 10. Konkret: hvordan det ville se ud på de to eksempler

**Vandtestsiden**
Pitch tre vinkler (§1), vælg "Rapporten". Motiv: laboratorie/rapport — koldt lys, klinisk,
data-drevet. Higgsfield genererer ét hero-shot (glas vand i klinisk lys), og alle øvrige
assets kædes fra det. Én pinned scrubbed scene i mekanisme-sektionen hvor vandet ændrer sig.
Tæller på kategori-stat. Verificér på 390px før nogen ser den.

**Advertorial**
Pitch tre vinkler, vælg fx "Journalisten der testede det". Motiv: redaktionelt — dagslys,
uposeret, kornet. Samme design-tokens, helt anden billedverden. Ingen pinned scene overhovedet
— advertorials skal læses som tekst, ikke opleves. Char-split på headline, clip-path på
billedrækker, ellers ro.

Samme skill, samme system, to sider der ikke ligner hinanden. **Det** er hvad
scroll-film-studio kan lære os — ikke filmen.
