import { APP_NAME } from '../config/brand'

// Public (unauthenticated) privacy policy — kept reachable without signing
// in for cases where a reviewer or third-party integration needs a URL for
// one before it can be approved.
//
// Written against what this app actually does rather than generic
// boilerplate. If the data model changes materially, this page should
// change with it.
//
// PLACEHOLDERS: the legal entity name and the governing-law jurisdiction are
// marked below and must be confirmed before this is relied on. This page is
// a plain, accurate description of the app's data handling — it is not
// legal advice and has not been reviewed by a lawyer.
const LAST_UPDATED = 'August 21, 2026'
const CONTACT_EMAIL = 'support@example.com'

function Section({ title, children }) {
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-gray-600">{children}</div>
    </section>
  )
}

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-gray-50 py-10">
      <div className="mx-auto max-w-3xl px-5 sm:px-8" data-testid="privacy-policy-page">
        <div className="rounded-xl border border-gray-200 bg-white p-6 sm:p-10">
          <h1 className="text-2xl font-bold text-gray-900">Privacy Policy</h1>
          <p className="mt-1 text-xs text-gray-400">Last updated: {LAST_UPDATED}</p>

          <p className="mt-6 text-sm leading-relaxed text-gray-600">
            {APP_NAME} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) provides software that
            franchises and their studios use to manage staff, users, and billing. This
            policy explains what information the service holds, why, and what choices
            you have.
          </p>

          <Section title="Who controls the data">
            <p>
              Each franchise and studio that uses {APP_NAME} controls its own
              records. We host and process that information on their behalf. If you
              are a member of a franchise or studio and want to see, correct, or
              delete your records, contact them directly — they can action it, and we
              will assist them.
            </p>
          </Section>

          <Section title="Information we hold">
            <p><strong>Accounts.</strong> Name, email address, role, and a securely
            hashed password. Staff may also have a short PIN used to sign in on a
            shared studio device. Passwords and PINs are stored hashed, never in
            readable form.</p>
            <p><strong>Organization records.</strong> Franchise and studio names,
            addresses, and contact details, and how users are assigned across that
            hierarchy.</p>
            <p><strong>Billing records.</strong> Subscription and pricing information
            processed through Stripe. We do not store full payment card details
            ourselves.</p>
            <p><strong>Usage and security records.</strong> Sign-in events and basic
            technical logs, kept so we can investigate problems and unauthorized
            access.</p>
            <p>
              We do not use this information to build advertising profiles or sell it
              to anyone.
            </p>
          </Section>

          <Section title="Where the information comes from">
            <p>
              Most information is entered directly by staff and administrators in
              the app.
            </p>
          </Section>

          <Section title="How we use it">
            <p>
              To run the service: showing the right users and organization
              structure to the right people, processing subscriptions and billing,
              sending account emails such as invitations and password resets, and
              keeping the service secure and working.
            </p>
          </Section>

          <Section title="Service providers">
            <p>
              We use a small number of providers to operate the service: a cloud
              hosting provider for the servers and database, an email delivery
              provider for account emails, and Stripe for billing. They may process
              information only as needed to provide those services to us.
            </p>
          </Section>

          <Section title="Keeping information safe">
            <p>
              Traffic to the service is encrypted in transit. Passwords and PINs are
              stored hashed. Access is restricted so a franchise or studio can only
              see its own users and records. No system can promise perfect security,
              but we take these measures seriously and fix problems promptly.
            </p>
          </Section>

          <Section title="How long we keep it">
            <p>
              We keep records for as long as the account uses the service. An
              administrator may ask us to delete their organization&apos;s data, and
              we will do so within a reasonable period, other than records we must
              keep for legal or security reasons.
            </p>
          </Section>

          <Section title="Your choices">
            <p>
              Depending on where you live, you may have the right to access, correct,
              export, or delete your personal information, or to object to certain
              processing. Members of a franchise or studio should contact their
              administrator first, as they control those records. You can also reach
              us at the address below and we will help.
            </p>
          </Section>

          <Section title="Changes to this policy">
            <p>
              If we make a material change we will update the date at the top of
              this page and, where appropriate, notify accounts in the app.
            </p>
          </Section>

          <Section title="Contact">
            <p>
              Questions about this policy or your information:{' '}
              <a className="font-medium text-blue-600 underline" href={`mailto:${CONTACT_EMAIL}`}>
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </Section>
        </div>
      </div>
    </div>
  )
}
