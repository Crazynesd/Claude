# Analyse: Hvad vi kan tage fra `scroll-film-studio` til Qleer-sider

**Formål:** Skillet `scroll-film-studio` bygger hele hjemmesider hvor siden er én lang
cinematisk indstilling der scrubber på scroll. Det er *ikke* det vi skal bruge. Men
processen, lovene og Higgsfield-pipelinen indeni er stærke — og de kan destilleres til
noget der gør vores **page-produktion** (vandtjek-siden, advertorials, nye sidetyper)
markant bedre.

Dette dokument er en analyse og en anbefaling. Intet er implementeret.

---

## 0. Udgangspunktet: hvad Qleer faktisk er

Hentet fra butikken, så analysen står på fakta og ikke hukommelse:

| | |
|---|---|
| Brand | **Qleer** — dansk vandfilter, DKK |
| Produkter | Hanefilter (549 abo / 750 engangs) · Brusefilter (649 / 850) · Patron (225, skiftes hver 3. måned) · Startpakke (medlemskab, 2-6 filtre, 999-2.499) |
| Farver | Juicy Coral · Mint · Water Blue · Bubblegum · Deep Blue Grey · Crisp White · Brushed Silver · Matte Black |
| Forretningsmodel | **Medlemskab.** Første patron er med i prisen, ny patron automatisk hver 3. måned, pause eller opsig når du vil |
| Sider i dag | `tjek-mit-vand` (template `vandtjek`), `produkter`, `abonnement`, `om-qleer`, `faq` |

To ting følger direkte af den tabel, og de vender to af antagelserne i vores nuværende
`gpp-builder` på hovedet. De står i §9 — læs dem før noget bygges.

---

## 1. Den centrale forskel man skal holde fast i

| | scroll-film-studio | Qleer-sider |
|---|---|---|
| Output | Et helt website | **Én side ad gangen** |
| Succeskriterie | Wow, "hvordan har de lavet det" | **Tilmelding til medlemskabet** |
| Brand | Nyt univers per build | **Ét brand, mange sider** |
| Vægt-budget | Ubegrænset (300 frames ≈ 20-40 MB) | **Mobil på 4G, LCP < 2,5s** |
| Sandheden er | Filmen ("siden er en afspiller") | **Argumentet og tilbuddet** |

Alt herunder er filtreret gennem den tabel. Når en mekanik fra skillet kun tjener æstetik,
ryger den ud. Når den tjener *klarhed, tempo eller troværdighed*, tager vi den.

---

## 2. Det største enkeltstående tyveri: **koncept-pitchet før byg** (skillets STEP 1)

Skillet bygger aldrig noget før det har pitchet **2-3 navngivne koncepter** med en konkret
gennemgang af hvad man rent faktisk *ser* — ikke en tese, men en scroll-fortælling. Ét
koncept markeres eksplicit **"(Anbefalet)"**, og brugeren kan altid sige "du vælger".

**Hvorfor det er guld for os:** `gpp-builder` går direkte fra intake-tabel til 20+ sektioner
Liquid. Hvis vinklen er forkert, opdager vi det efter 2.000 linjer kode. Et pitch koster 30
sekunder og fanger det før.

**Oversat til vandtjek-siden** (som allerede findes på `tjek-mit-vand` — så det her er lige
så meget en gentænkning som en ny side):

- **"Rapporten"** *(Anbefalet)* — siden er formet som en vandrapport på læserens egen adresse.
  Åbner med et resultatkort med deres postnummer. Scroll: hvad tallene betyder → hvad
  vandværket ikke måler for → hvorfor et filter kun virker så længe patronen er frisk →
  medlemskabet som svaret. Passer til at siden allerede hedder "Tjek mit vand" — den leverer
  bare på løftet nu.
- **"Det du ikke kan se"** — visuelt drevet. Åbner på et glas rent vand i makro, scroll zoomer
  ind til man ser hvad der faktisk er i det. Hårdere hook, tungere på billeder.
- **"Fra hane til bruser"** — dækningsvinklen. Starter i køkkenet, følger vandet gennem
  hjemmet, ender ved bruseren. Sælger Startpakken (flere filtre) frem for ét enkelt filter,
  og udnytter at prisen falder pr. stk. jo flere man tager.

Samme produkt, samme tilbud, tre helt forskellige sider. **Det valg skal træffes før
byggeriet, ikke undervejs.**

---

## 3. Interviewet med "du bestemmer"-udgang (skillets STEP 0)

Skillets interview har en regel værd at kopiere ordret:

> *Hvert kreativt spørgsmål har en "du bestemmer"-vej. Blokér aldrig på et designsvar du selv
> kan give godt.*

Vores intake i `gpp-builder` er ren faktaindsamling (persona, pris, offer). Det er rigtigt og
skal blive. Men der mangler ét spørgsmål, oversat:

> **"Rejsen — hvor starter læseren, og hvor ender de?"** Ikke sektionsrækkefølgen, men
> *transformationen*: fra "jeg tænker ikke over mit vand" til "jeg kan ikke leve med det her".

Det er dét spørgsmål der gør forskellen på en side der lister argumenter og en side der
fortæller noget. Det er også det eneste sted skillets "one continuous shot"-tankegang faktisk
giver mening hos os: **ikke ét kamera, men ét ubrudt argument.**

---

## 4. Den gyldne regel + delegationsmodellen — tages næsten ordret

Skillet er meget skarpt på hvad der må uddelegeres:

| Arbejde | Hvem | Vores oversættelse |
|---|---|---|
| Koncept, copy, sektionsdesign, Liquid, endeligt review | **Claude — aldrig uddelegeret** | Uændret |
| Første udkast: ét afsnit, ét FAQ-sæt, én testimonial-blok | **Subagents — og du omskriver hvert udkast; intet fra en subagent shipper uredigeret** | Uændret. Den vigtigste sætning i hele skillet |
| Billed-/videogenerering | (Higgsfield) | **Higgsfield MCP** |
| Screenshots, vægt-måling, upload, verifikation | **Ren kode, ingen model** | Puppeteer + Shopify GraphQL |

"Second-model sparring" (at spørge en anden frontier-model om at angribe pitchet) — dropper vi.
Lav værdi på en konverteringsside, og det tilføjer afhængigheder.

---

## 5. Verifikations-harnesset — det største hul i vores nuværende workflow

Det her mangler vi mest, og skillet har den bedste formulering af hvorfor:

> **"Bed aldrig brugeren om at kigge efter noget du kan bevise."**

Skillets kontrakt er tre ting:
1. `?jump=<scrollY>` → siden lander præ-scrollet med al scroll-state tvunget på plads
2. `window.__ready = true` → fyrer først når siden faktisk er klar
3. `verify.js` → puppeteer + system-Chrome, screenshot ved enhver position + jank-test

Plus en vigtig teknisk pointe: **preview-paneler throttler skjulte faner** (rAF fryser →
forældede screenshots). Derfor eksisterer harnesset overhovedet.

**Oversat til Qleer:** vi uploader til draft-theme og … kigger. I stedet:

- Screenshot af preview-URL'en ved hver sektion, **mobil først (390×844)** — det er dér den
  betalte trafik er — derefter desktop.
- Erstat jank-testen med en **vægt- og LCP-gate**: total sidevægt, LCP, CLS. En side der vejer
  6 MB er en dyrere fejl end en der hakker.
- Faste tjek der kan *bevises* frem for vurderes: er CTA over folden på mobil? Renderer
  prisblokken? Står abonnements-vilkåret ("pause eller opsig når du vil") synligt ved CTA'en?
  Åbner FAQ-accordion? Er der vandret overflow?
- Qleer-specifikt: **farvevælgeren**. Otte colorways betyder otte varianter der kan rendere
  forkert. Det skal screenshottes, ikke antages.

Det er ~80 linjer Node og fjerner hele "kan du lige tjekke om den ser rigtig ud"-runden.

---

## 6. Motion-ordforrådet — tag udvalgt, smid resten

`engine.md` har et helt bibliotek af scroll-motion. `gpp-builder` har præcis **én** primitiv:
`.pl-reveal` fade-up via IntersectionObserver. Det er tyndt. Herfra tager vi:

**Tag med:**
- **Char-split headline-reveal** på hero — headline splittes i spans, staggered
  `yPercent:120 → 0` med `power4.out`. Kører én gang, ikke scroll-afhængig. Premium-følelse
  for ~0 kb.
- **Clip-path reveal** (`inset(0 0 100% 0) → inset(0)`) til editorial-rækker — perfekt til
  før/efter og rapport-sektionen.
- **Tællere** med `snap: { textContent: 1 }` og `once: true` — et tal der tæller op er
  billigere end et diagram og læses hurtigere.
- **Én — og kun én — pinned scrubbed scene per side**, og kun hvor transformationen *er*
  argumentet. Hos Qleer er der præcis ét sådant sted: **vandet der løber gennem patronen.**
  Det er hele produktet vist på tre sekunder. Alt andet pin er dekoration.
- **Ordre-loven, ordret:** ScrollTriggers refreshes i oprettelsesrækkefølge — opret alle
  pinned scener **først**, ambient/baggrund **bagefter**. Ellers beregnes positioner før
  pin-spacers findes, og alt efter pinnen sidder tusindvis af pixels forkert. Stille fejl.
- **`prefers-reduced-motion`** i hvert build. Mangler helt hos os i dag.

**Smid væk:**
- Velocity-skew, marquee-drift, horisontale pinned runs — dekorativ støj på en side der skal
  sælge.
- **Lenis smooth-scroll** — flag som risikabelt. Det kaprer scroll og opfører sig
  uforudsigeligt i Meta/TikTok in-app-browsere, som er præcis dér vores trafik kommer fra.
  Skillet gør det til standard; vi bør ikke.

---

## 7. Sømme og sticky header — to mekanikker der generaliserer godt

**Sømløs overgang (film → indhold):** skillet sampler den sidste frames bundfarve og starter
næste sektions baggrund på præcis den hex, plus en bundfade der ramper ind over de sidste 8%.

Generaliseret til os: sider bygget af skiftende farvebånd er i dag bare *stablet*.
**Overgangs-disciplin** — en gradient-landingszone der smelter det ene bånd over i det næste
i stedet for en hård kant — er forskellen på "designet" og "sammensat af sektioner". Gratis at
indføre, ren CSS. Særligt relevant for Qleer fordi paletten er kulørt: hårde kanter mellem
Mint og Juicy Coral ser billigt ud, en overgang ser bevidst ud.

**Adaptiv header:** skillet sampler frame-luminans hver ~180 ms og skifter en `.on-light`-klasse,
hvor alle header-farver kører gennem `currentColor` så én klasse vender det hele.

Vi behøver ikke canvas-sampling — vores baggrunde er kendte. Men *mønstret* er rigtigt: én
`.on-light`-klasse skiftet af en IntersectionObserver på hero-sektionen, alle farver via
`currentColor`. Med otte colorways bag topbaren er en hardkodet header-farve garanteret forkert
et sted.

---

## 8. Higgsfield — her ligger den store gevinst, men den skal vendes om

Det er her skillet er mest værdifuldt for os, og samtidig mest misforstået hvis man tager det
bogstaveligt. I skillet producerer Higgsfield en 5-kapitels sammenhængende **video** → 300
frames → canvas-scrubber. **Det output er forkert for os.** Men pipelinen bagved er rigtig.

### 8.1 Stills som asset-fabrik, ikke video
Higgsfields billedgenerering bliver kilden til det vi i dag mangler: hero-billeder, filteret
monteret i et rigtigt køkken, vandet i makro, før/efter, patronskiftet, badeværelset,
portrætter til testimonials. **En asset-fabrik per side** er langt mere værd for Qleer end en
scroll-film nogensinde bliver — især fordi produktet er fysisk og skal ses i en bolig for at
give mening.

### 8.2 Kædeloven overlever — men med nyt formål
Skillets lov: hvert klips `--start-image` er den *bogstavelige* sidste frame af det forrige —
ikke et lookalike-keyframe, de faktiske pixels. Formålet dér er video-kontinuitet.

**Oversat til os:** generér hero-billedet først, og brug det som start-/referencebillede for
**alle andre billeder på siden**. Så ser hele siden ud som ét fotoshoot i stedet for otte
stock-billeder. Det er skillets *"ét univers per brand"* korrekt oversat: **ét univers per
side.** Brandet er konstant, motivet varierer per sidetype.

Og her har Qleer en gave skillet ikke har: **colorwayen er motivet.** En side kan ankres til
Mint (køkken, køligt dagslys, lyse flader), en anden til Juicy Coral (varmere, mere legende,
yngre persona), en tredje til Matte Black (dyrere, mere designbevidst). Samme brand,
øjeblikkeligt forskellige verdener — og det matcher et produkt kunden faktisk skal vælge
farve på.

### 8.3 SSIM-porten → en brand-konsistens-port
Man kan ikke SSIM'e to forskellige motiver. Men princippet — **mål, kig ikke** — oversættes:
sample hvert genereret assets palette og luminans og tjek at det ligger inden for sidens valgte
colorway. Off-brand assets afvises og genereres igen *før* de ryger i Liquid'en, ikke efter at
nogen har set siden.

### 8.4 Hvis der overhovedet skal video på
Ét enkelt 3-5s loop, muted, autoplay, med poster-frame og lazy loading — vandet gennem
patronen, eller monteringen på under et minut. **Ikke** en 300-frames scrubber. Vægt-budgettet
afgør det, ikke smagen.

### 8.5 Omkostningsdisciplinen tages 1:1
1. **Audio OFF** — audio ~3-dobler regningen i stilhed.
2. **Bekræft før forbrug** — oplys totalen før generering, vis kvitteringen efter.
3. **Draft billigt, master én gang** — validér på laveste tier, kør kun godkendte prompts i
   fuld opløsning.
4. **Genbrug materialet** — og her har vi en bonus skillet ikke har: ét asset-sæt driver
   **vandtjek-siden, advertorialen og annoncerne**. Materialet er omkostningen; genbrug er gratis.

Plus den praktiske: **~15% af Higgsfield-jobs fejler server-side uden grund og bliver ikke
faktureret — prøv bare igen.** Værd at have skrevet ned, ellers fejlsøger man noget der ikke er
i stykker.

---

## 9. To ting i `gpp-builder` der er direkte forkerte for Qleer

Det her ligger uden for scroll-film-analysen, men det rammer anbefalingen i §10, så det skal stå:

**9.1 Abonnements-reglen er vendt på hovedet.** `references/offer-rules.md` foreskriver en
nudge-boks der lyder: *"Ingen abonnement — nogensinde. Konkurrenter tager X kr/år."* Det var et
salgsargument for det gamle brand. **For Qleer argumenterer det imod vores egen
forretningsmodel.** Qleer *er* medlemskabet: patronen skiftes hver 3. måned, første patron er
med i prisen, og abonnementsprisen er billigere end engangskøb (549 vs. 750 på hanefilteret).

Den rigtige framing er ikke "intet abonnement" men **"du skal ikke tænke over det"**: filteret
virker kun så længe patronen er frisk, så vi sender den automatisk — og du kan pause eller
opsige når du vil. Frihed frem for fravær. Den ene sætning skal skiftes, ellers bygger vi sider
der sælger imod os selv.

**9.2 Designsystemet er tonalt forkert.** `references/design-system.md` beskriver mørk
(`#111318`) + roseguld + Raleway — et dæmpet premium-udtryk. Qleers palet er Juicy Coral, Mint,
Bubblegum, Water Blue. Det er et lyst, legende, kulørt brand. Farvetokens, typografi og
bamse-SVG'erne skal erstattes fra bunden.

**Åbent punkt:** de præcise hex-værdier for Qleers colorways ligger i theme-settings og kunne
ikke hentes via Admin API. De skal pinnes fra temaet før et nyt designsystem skrives ned — jeg
har bevidst ikke gættet dem.

---

## 10. Hvad vi eksplicit skal droppe fra scroll-film-studio

- **"Hele siden er ét shot"** — præmissen. 850vh scroll-drivere hører ikke hjemme på en
  konverteringsside.
- **Canvas frame-scrubberen** (300 JPEGs, ImageBitmap sliding window, DPR-cap, lerped playhead).
  Teknisk imponerende, 20-40 MB. Dødsdom for Meta-trafik på mobil.
- **Nye fonte og palet per build.** Skillet siger "aldrig to brands der ligner hinanden" — hos os
  er det modsatte sandt: Qleer-identiteten er konstanten. Variationen ligger i colorway, motiv og
  sektionsarkitektur.
- **Vercel-deploy** — vi shipper til Shopify draft-theme.
- **"Footage-first"-loven** ("filmen er sandheden, siden er en afspiller") — vendes om:
  **tilbuddet og argumentet er sandheden; billederne tjener dem.**

---

## 11. Anbefaling

Byg ikke et nyt skill ved siden af. **Ombyg `gpp-builder` til Qleer** — i denne rækkefølge:

1. **Ret de to forkerte antagelser først** (§9). Abonnements-framingen er en aktiv skade, ikke
   bare forældet. Intet andet betyder noget før den er væk.
2. **Koncept-pitch som nyt trin mellem intake og byg** (§2). Størst effekt, mindst arbejde.
3. **Verifikations-harness** — `?jump` + `__ready` + screenshot- og vægt-gate (§5). Fjerner den
   manuelle QA-runde helt.
4. **Ny reference `motion.md`** — det udvalgte motion-ordforråd, ordre-loven,
   `prefers-reduced-motion`, overgangs-disciplin og adaptiv topbar (§6-7).
5. **Ny reference `asset-pipeline.md`** — Higgsfield som asset-fabrik: hero-først-kæden,
   colorway som motiv, brand-konsistens-porten, omkostningsdisciplinen (§8).

Punkt 1-3 kan stå alene og giver værdi fra første side. Punkt 4-5 er dér den visuelle kvalitet
reelt løftes.

---

## 12. Konkret: hvordan det ville se ud på to sider

**Vandtjek-siden** (`tjek-mit-vand`)
Pitch tre vinkler (§2), vælg "Rapporten". Colorway: Water Blue — køligt, klinisk, dataagtigt.
Higgsfield genererer ét hero-shot (glas vand i køligt dagslys) og kæder alle øvrige assets fra
det. Én pinned scrubbed scene: vandet gennem patronen. Optællende tal på kategori-stat.
Abonnementet framet som "du skal ikke tænke over det", ikke som binding. Verificér på 390px før
nogen ser den.

**Advertorial**
Pitch tre vinkler, vælg fx "Jeg troede vores vand var fint". Colorway: Juicy Coral — varmt,
uposeret, hverdagsagtigt. Samme design-tokens, helt anden billedverden. Ingen pinned scene
overhovedet — advertorials skal læses som tekst, ikke opleves. Char-split på headline,
clip-path på billedrækker, ellers ro.

Samme skill, samme system, to sider der ikke ligner hinanden. **Det** er hvad
scroll-film-studio kan lære os — ikke filmen.
