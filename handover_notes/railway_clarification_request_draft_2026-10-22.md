# مسودة طلب إيضاح إلى Railway — لا تُرسَل إلا بيد المالك

ملخص عربي (خمسة أسطر):
1. الطلب يسأل Railway كتابياً: هل حسابنا ومشروعنا ضمن الفئة المتأثرة فعلاً؟
2. يطلب تحديد المتغيرات التي فُكّ تشفيرها لحسابنا، والمدة، وما إذا كان قد حدث نسخ أو استعمال.
3. يطلب سجلات الوصول المتاحة وموعداً تقديرياً لاستعادة البناء لمنطقة مشروعنا.
4. يسأل عن إقليم sjc وعن موضع تخزين النسخ والسجلات، لحاجتنا إلى تقييم نقل البيانات عبر الحدود.
5. بلا أسرار ولا بيانات شخصية، ويحمل مهلة رد قصيرة لأن لدينا التزام إخطار نظامي خلال 72 ساعة.
قبل الإرسال يملأ المالك الأقواس المربعة ويراجع النص بنفسه، ويُرسل من حسابه إلى القناة الرسمية في بريد الإفصاح.

---

Subject: Security disclosure of 21 Oct 2026: request for account-specific scope confirmation (account owner: [OWNER NAME])

Hello Railway Security / Support team,

We received your email "Urgent: Railway Security Disclosure - Rotate Credentials" on 22 October 2026 at 02:58 (time zone as shown in the email: [CONFIRM]). We operate a production school-management application on Railway that processes personal data of minors and staff, so we are assessing a statutory breach-notification obligation under Qatar's Personal Data Privacy Protection Law (Law No. 13 of 2016), which is time-bound (72 hours). To complete that assessment we need account-specific answers.

Account / project identifiers (no secrets):
- Account email: [OWNER ACCOUNT EMAIL]
- Project: [PROJECT NAME / ID]
- Environment: production
- Services: three application services (web, worker, scheduler), one PostgreSQL service, one Redis service
- Region: US West (sjc) per our configuration

Please confirm in writing:
1. Is our account / project among those affected? If you are still determining this, when will you know?
2. Which environment variables (by variable name only, per service) were accessed, and for which were the decrypted values obtained? Were database credentials and application encryption/signing keys among them?
3. The time window of the unauthorized access, and whether you have evidence of the data being copied, used, or used to connect to our services or databases.
4. Any access logs, audit-log entries, or indicators of compromise relating to our project that you can share (source IPs, timestamps, actions), and whether the revocations that appear under a Railway employee's name in our audit log relate to this event.
5. Estimated restoration time for builds and redeploys in our region, and the expected order of restoration for our plan tier.
6. Data location: confirm where our environment-variable store, database volumes, backups and logs are physically stored (our configuration is the sjc region), and whether any of it is replicated or processed in other regions. We need this for our cross-border transfer assessment.
7. Whether you will contact us directly with a formal affected-customer notice, and the official channel and contact person for follow-up questions.

Given our statutory deadline, we would be grateful for a reply by [DATE/TIME — suggest 2026-10-23 12:00 Qatar time]. Please do not include any secret values or personal data in your reply; names and timestamps are sufficient.

Regards,
[OWNER NAME]
[ROLE / ORGANIZATION]
[CONTACT]
