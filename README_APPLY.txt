Malita — final domain setup: malitatech.co.za
==================================================

Congrats on the domain. Here's everything left to do, in order.

Step 1 — Apply the CNAME file
1. Copy docs/CNAME from this tarball into your local clone (already
   contains exactly "malitatech.co.za").
2. git add docs/CNAME
   git commit -m "Update CNAME to malitatech.co.za (final domain purchased)"
   git push

Step 2 — Point DNS at GitHub Pages
In Afrihost's ClientZone: Hosting -> malitatech.co.za -> Hosting
Settings -> DNS editor. Add these (Create New Record for each):

  Type: A      Host: @ (or blank)   Value: 185.199.108.153
  Type: A      Host: @ (or blank)   Value: 185.199.109.153
  Type: A      Host: @ (or blank)   Value: 185.199.110.153
  Type: A      Host: @ (or blank)   Value: 185.199.111.153
  Type: CNAME  Host: www            Value: sbugzoh2.github.io.

(All four A records at the apex is correct and normal - GitHub Pages
load-balances across them. The www CNAME is optional, only needed if
you also want www.malitatech.co.za to work alongside the bare domain.)

If you picked "Domain Parking" at checkout like I suggested, this DNS
editor should already be available to you with no extra product needed.

Step 3 — Enable the custom domain on GitHub
On GitHub: Settings -> Pages -> Custom domain -> malitatech.co.za ->
Save. GitHub may also auto-detect it from the CNAME file once you've
pushed it. "Enforce HTTPS" will only become available once DNS has
actually propagated and GitHub can see it (can take anywhere from a few
minutes to a few hours) - check back and tick it once it appears.

Then check https://malitatech.co.za loads your landing page.

Step 4 — Verify in Google Search Console
1. https://search.google.com/search-console
2. Add malitatech.co.za as a "Domain" property (not "URL prefix").
3. Add the TXT record it gives you in Afrihost's DNS editor
   (Type: TXT, Host: @, Value: <from Search Console>).
4. Wait for DNS to propagate, then click Verify.

Step 5 — Play Console
Enter malitatech.co.za as your developer website in Play Console's
account setup. It should now pass verification.

Let me know once DNS is added and I can help check it's resolving
correctly before you move on to Search Console.
