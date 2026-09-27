# Assets

Official Encalm branding used by the app (see `modules/ui.py`):

| File | Used for |
|---|---|
| `encalm_logo.png` | Original stacked logo (gold mark + navy ENCALM) — sign-in page |
| `encalm_logo_horizontal_light.png` | Mark + white wordmark side by side — navy sidebar (`st.logo`) |
| `encalm_mark.png` | Gold petal mark only — collapsed sidebar icon and browser-tab favicon |

The two derived files are exact crops/recolours of `encalm_logo.png`.
If the logo changes, replace `encalm_logo.png` and regenerate the other two
(same crop: mark = top part, wordmark = bottom part; wordmark recoloured white).

Brand colours (sampled from the logo): navy `#142248`, gold `#CBA578`.
Font: Montserrat (Google Fonts), the closest free match to the wordmark.

## Icons

`icons/` holds the [Lucide](https://lucide.dev) icons used for the sidebar
pages, tabs and page headers — unmodified SVGs from `lucide-static` 1.48.0
(ISC licence, see `icons/LICENSE`). They are drawn via CSS masks
(`modules/ui.py`: `sidebar_nav_icons`, `tab_icons`, `icon_html`), so they take
the surrounding text colour. To add one, copy its SVG from lucide.dev into
`icons/` and refer to it by file name (without `.svg`).
