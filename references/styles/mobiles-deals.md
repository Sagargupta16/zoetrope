# S-mobiles-deals · 9:16 narrated deals roundup (92 s)
**Source:** our own build, no external source · our build: mobiles-deals
**Use when:** "deals video", "top offers roundup", "price drop list", "festival sale reel", "vertical product-by-product ad"
**Defaults:** about 90 s (33 s and 30 s short cuts also built) · 9:16 1080x1920 · 30 fps · narrated plus music

## The brief (reusable prompt)
Make a vertical English video of the best offers on {store page or category}: a hook, one card per product with struck price and deal price, a bank or coupon offer card, a wall of everything, and a shop-now end card. Voiceover on every product.

## Scene plan
122 BPM (beat 0.4918 s). Each section length is the speech at 1.04x plus a hold, rounded up to 2 beats; product cards are on screen 3.0 to 4.9 s.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-3.9 | Hook | "Buying a phone? Watch this first." with rays and a shake |
| 3.9-8.9 | Opener | Sale lockup |
| 8.9-15.7 | Price hook | Flagship M.R.P struck, "Now?" |
| 15.7-23.6 | Flagships 1 and 2 | Deal price cards; groove drops in |
| 23.6-59.0 | Deals 03 to 10 | One card each, 3.9 to 4.9 s, "Phone deal 03 / 10" counter |
| 59.0-63.9 | Bank offer | Instant discount and cashback card |
| 63.9-76.7 | Accessories 1 to 3 | One card each |
| 76.7-86.6 | Wall | 10 phones and 3 accessories in one grid; narration gives the page address |
| 86.6-90.5 | End card | "Shop now, before they're gone!" |

## Look
- Palette used in the build: sun yellow #ffd000, deep ink #0d0614, magentas #c2185b, #be1e66, #a3164f, blue #2a6be0, navy #0c2d72, red #e0102f, teal #00a3a3.
- Type: Avenir Next, Helvetica Neue, Arial (Mac system).
- Layout and texture: product photo (user supplied, 900 px square) on a card with struck M.R.P, deal price, percent off.

## Motion
Hook: scale 2.2 to 1 with 4 degree rotation over 0.4 beat (ease-out quart: 1 - (1 - k) ** 4, a touch softer than ease_out_expo) plus a quick shake (0.03 s steps, 6 swings). Wipes: ease_out_cubic in over 0.5 beat, ease-in out over 0.6 beat. Small per-beat scale punches easing out over 0.8 beat. Use Indian digit grouping (1,29,999) for Indian stores.

## Audio
122 BPM house bed (the build used a licensed track); groove drops at the first product (15.74 s). Voice via text-to-speech at 1.04x, 90 Hz high-pass, music ducked 8 dB (40 ms attack, 300 ms release), voice +2 dB, limiter, -14 LUFS. The build used the voice Ryan (an earlier cut used Matthew). Voices differ in pace, so generate each line first and set section lengths from the real clip durations.

## Build notes
Order: schedule first (clip length to section length), then music, then pictures. Product images come from the user, never scraped. Mark offer-inclusive prices with a star and footnote; use the live page price and M.R.P, and record any tile/page mismatch.

## Pitfalls (from what went wrong in our build)
- Tile prices differ from product-page prices and change during a sale: re-check before posting and say prices are time-limited.
- Counter leading zeros were dropped ("03" became "3"): pre-draw the card counters as text.
- Retailer logos, GIFs and brand marks need approval from the brand owner for external use.

## Style QA
- Every price on a card matches the narration.
- Each section length equals its voice clip plus hold, rounded to 2 beats.
