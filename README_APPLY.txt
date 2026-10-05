Malita — a real website for Google Play Console verification
================================================================

The problem you described: Play Console wants to verify your developer
website, and a Streamlit app URL can't be verified there - Streamlit
Cloud doesn't let you place a DNS TXT record or an arbitrary
verification file at your domain's root, which is exactly what website
verification needs.

The good news: you already have a real, working website you fully
control and that already passed the hard part (it's live, on HTTPS, you
own the repo it's served from) - GitHub Pages at docs/, which already
hosts your privacy policy. It was just missing an actual homepage. This
delivery adds one, plus fixes a real bug I found along the way.

What's in this tarball
------------------------
1. docs/index.html (NEW) - a proper one-page site: hero section, a
   feature grid covering all six of the app's actual modes (AI Tutor, AI
   Teacher, Practice Questions, Past Papers Library, Collaboration Forum,
   Learner Profile), a short "who it's for" section with your real CIPC
   registration number, and a footer linking to your existing privacy
   policy. Links to https://malita-maths.streamlit.app ("Try it on the
   web") since the Play Store listing isn't live yet - swap that for
   your real Play Store link once it is.

2. assets/favicon.png, mobile/assets/favicon.png, docs/favicon.png
   (FIXED) - all three had ended up holding the 1024x500 Play Store
   feature graphic instead of a small favicon (probably from copying
   that image around while prepping Play Store assets). A 1024x500
   image as a <link rel="icon"> renders broken in every browser - this
   regenerates all three as a proper 48x48 rounded-corner crop of your
   actual app icon. Worth fixing regardless of the website question,
   since it was live and broken on your actual deployed site/app.

How to apply
------------
1. Copy these files into your local clone, overwriting where they exist:
     docs/index.html        (new file)
     docs/favicon.png
     assets/favicon.png
     mobile/assets/favicon.png

2. From your repo root:
     git add docs/index.html docs/favicon.png assets/favicon.png mobile/assets/favicon.png
     git commit -m "Add a real landing page at docs/ for Google Play website verification, fix broken favicons"
     git push

3. Within a few minutes it'll be live at https://sbugzoh2.github.io/malita/
   (confirm GitHub Pages is still set to deploy from the `docs/` folder
   on your default branch - Settings → Pages in the repo).

You still need to do, on your side (I can't do these - they need your
own accounts/payment/DNS access)
---------------------------------------------------------------------------
A) BUY A DOMAIN. For a South African company, .co.za is the natural
   choice (cheap, ~R100-150/year, via registrars like domains.co.za,
   Afrihost, or Xneelo) - something like malita.co.za or
   malitaapp.co.za. A .com works too if you want international reach
   (Namecheap, Google Domains successor Squarespace Domains, etc.) and
   is sometimes easier to manage DNS for. Check your preferred name is
   actually available before anything else.

B) POINT THE DOMAIN AT GITHUB PAGES. Once you own it:
   - At your registrar's DNS settings, add either:
       - A CNAME record: www -> sbugzoh2.github.io  (if using a www
         subdomain), or
       - Four A records at the apex (@) pointing to GitHub Pages' IPs:
         185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153
   - In the repo: add a file named exactly `CNAME` (no extension) inside
     docs/, containing just your domain on one line, e.g.:
         malita.co.za
     (Tell me once you've bought the domain and I'll add this file and
     the exact DNS records for you - takes 2 minutes once I know the
     domain name.)
   - In GitHub: Settings → Pages → set the custom domain to the same
     value, and tick "Enforce HTTPS" once it's available (can take a
     few hours after DNS propagates).

C) VERIFY OWNERSHIP IN GOOGLE SEARCH CONSOLE (this is the actual
   "verification" Play Console is asking for):
   - Go to https://search.google.com/search-console, add your new
     domain as a property.
   - The fastest method once you own the domain: "Domain" property type
     + a DNS TXT record (Search Console gives you the exact value to
     add at your registrar - takes a few minutes to propagate, verifies
     the whole domain in one go, including any subdomain).
   - Alternative: "URL prefix" property + HTML file upload - Search
     Console gives you a file like google1234567890.html; send it to me
     and I'll drop it straight into docs/ for you, no DNS needed.

D) ADD THE DOMAIN TO PLAY CONSOLE. Once Search Console shows it
   verified, go back to Play Console's developer account setup and
   enter the new domain as your developer website - it should now pass
   verification.

Let me know once you've got a domain picked (or bought) and I'll handle
the CNAME file + give you the exact DNS records to paste in - that part
takes me two minutes once I have the domain name.
