# Ad Network Configuration
# Replace these with your actual ad codes when you get approved

# Google AdSense
ADSENSE_CLIENT_ID = "ca-pub-XXXXXXXXX"  # Replace with your AdSense publisher ID

# Alternative Ad Networks
MEDIA_NET_SITE_ID = "XXXXX"
PROPELLER_ADS_ZONE_ID = "XXXXX"

# Ad Codes - Replace the placeholder divs with these
AD_CODES = {
    'top_banner': '''
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={client_id}"
         crossorigin="anonymous"></script>
    <ins class="adsbygoogle"
         style="display:block"
         data-ad-client="{client_id}"
         data-ad-slot="XXXXXXXXX"
         data-ad-format="auto"
         data-full-width-responsive="true"></ins>
    <script>
         (adsbygoogle = window.adsbygoogle || []).push({});
    </script>
    '''.format(client_id=ADSENSE_CLIENT_ID),
    
    'rectangle': '''
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={client_id}"
         crossorigin="anonymous"></script>
    <ins class="adsbygoogle"
         style="display:block"
         data-ad-client="{client_id}"
         data-ad-slot="XXXXXXXXX"
         data-ad-format="rectangle"></ins>
    <script>
         (adsbygoogle = window.adsbygoogle || []).push({});
    </script>
    '''.format(client_id=ADSENSE_CLIENT_ID)
}
