# DISC Analyzer Skill

Analyserer kundeprofil og returnerer DISC-profil med sproglige anbefalinger.

## Rolle
Analyser kundens kommunikationsstil baseret på emailsprog, mødenoter eller beskrivelser. Returner præcis DISC-profil og sproglige anbefalinger.

## Inputs
- Emailtekst fra kunden
- Mødenoter om kunden
- Brugerens beskrivelse af kunden

## Output format
Returner altid på dansk:

**DISC-profil:** [primær] [eventuel sekundær]
**Konfidiens:** [Høj / Middel / Lav]
**Baseret på:** [kort forklaring]

**Sproglige anbefalinger:**
- Brug: [ord og vendinger der virker]
- Undgå: [ord der frastøder]
- Struktur: [hvordan mailen bygges op]

**Det de bekymrer sig mest for:** [hvad skal adresseres]

## DISC Reference
**D:** Kort, direkte, ROI-fokus. Bundlinje først.
**I:** Energi, storytelling, relation. Historie først.
**S:** Trygt, konkret, beroligende. Tryghed først.
**C:** Præcise tal, klare vilkår. Data først.
