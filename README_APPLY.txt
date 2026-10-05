Malita — malita.co.za domain setup
=====================================

Good choice. Here's the full path from "buying it at Afrihost" to
"Google Play Console verified", including the one file I've already
prepared for you.

Step 1 — Register the domain
------------------------------
On Afrihost's site, register malita.co.za. You don't need a hosting
package for this (co.za registration alone is enough) - you're pointing
it at GitHub Pages, not hosting on Afrihost's own servers.

Step 2 — Point DNS at GitHub Pages
-------------------------------------
Once it's registered, in Afrihost's ClientZone:
  Hosting -> [your domain] -> Hosting Settings -> DNS editor

Add these records (click "Create New Record" for each):

  Type: A      Host: @ (or blank)   Value: 185.199.108.153
  Type: A      Host: @ (or blank)   Value: 185.199.109.153
  Type: A      Host: @ (or blank)   Value: 185.199.110.153
  Type: A      Host: @ (or blank)   Value: 185.199.111.153
  Type: CNAME  Host: www            Value: sbugzoh2.github.io.

(Four A records at the apex, that's normal and correct for GitHub Pages
- it load-balances across all four. The CNAME for www is optional, only
needed if you also want malita.co.za and www.malita.co.za to both work.)

If Afrihost's DNS editor offers "Point via NS records" vs "Point via A
records" as a choice: pick A records (what's above) - NS pointing would
hand DNS control entirely to another provider, which you don't need
here since you're just adding a few records, not moving hosting.

DNS changes can take anywhere from a few minutes to a few hours to
propagate.

Step 3 — Apply the CNAME file + enable the custom domain on GitHub
----------------------------------------------------------------------
1. Copy the file in this tarball into your local clone:
     docs/CNAME
   (already contains exactly "malita.co.za" - this is what tells GitHub
   Pages which domain to answer to.)

2. From your repo root:
     git add docs/CNAME
     git commit -m "Add CNAME file for malita.co.za custom domain on GitHub Pages"
     git push

3. On GitHub: Settings -> Pages -> under "Custom domain", enter
   malita.co.za and save (it may already show it automatically once it
   sees the CNAME file). Once DNS has propagated, tick "Enforce HTTPS" -
   this option only appears once GitHub can see the DNS pointing
   correctly, so it may take a few hours to show up.

4. Check https://malita.co.za loads your new landing page.

Step 4 — Verify ownership in Google Search Console
-------------------------------------------------------
1. Go to https://search.google.com/search-console
2. Add malita.co.za as a "Domain" property (not "URL prefix" - the
   domain property type is the one that uses a DNS TXT record and
   verifies the whole domain at once).
3. Search Console gives you a TXT record value - add it in Afrihost's
   DNS editor the same way as the records above (Type: TXT, Host: @,
   Value: <what Search Console gives you>).
4. Wait for DNS to propagate, then click Verify in Search Console.

Step 5 — Add the domain to Play Console
--------------------------------------------
Back in Play Console's developer account setup, enter malita.co.za as
your developer website. It should now pass verification since Search
Console confirms you own it.

If anything doesn't match what you see on Afrihost's actual interface
(registrars change their UI from time to time), their own help article
is here: https://help.afrihost.com/entry/how-to-point-a-domain - happy
to help troubleshoot once you're in there.
