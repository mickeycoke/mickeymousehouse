import AppShell from '../components/layout/AppShell'
import PageHeader from '../components/layout/PageHeader'
import { APP_NAME } from '../config/brand'

// In-app how-to guides for admins and studio owners. Describes the real
// onboarding flows: inviting instructors and setting them up with a password.

const GUIDES = [
  {
    // The floor here mirrors vite.config.js `build.target` (consistent
    // support from 2020-era devices) — change both together.
    id: 'system-requirements',
    title: 'System requirements',
    intro: `${APP_NAME} runs on phones, tablets, and computers back to about 2017. Newer browsers (2020 or later) get the best, fastest interface; older ones get a compatible version of every screen.`,
    steps: [
      'iPhone / iPad — best experience: iOS 14 or newer (iPhone 6s, iPad Air 2, iPad mini 4, or anything newer). Keep devices updated in Settings → General → Software Update.',
      'iPhone / iPad — still supported: iOS 11 to 13 (iPad Air 1, iPad mini 2/3, iPhone 5s/6). Every screen works; some visual polish is reduced.',
      'Android tablet / phone: Chrome from 2020 or newer for the best experience (Chrome updates itself via the Play Store); older Chrome still works.',
      'Computer: Chrome, Edge, Firefox, or Safari from 2020 or newer for the best experience. Internet Explorer is not supported.',
      'If a screen ever looks blank or broken on a saved home-screen app: delete the icon, open the site fresh in the browser, and Add to Home Screen again.',
    ],
    notes: [
      'Devices that cannot reach iOS 11 (original iPad Air is fine; iPad 2/3/4 and iPad mini 1 are not) cannot run the app.',
      'Front-desk tablets: when replacing hardware, anything that can update to the current iOS/Android gets the best experience.',
    ],
  },
  {
    id: 'invite-instructor',
    title: 'Invite a new instructor',
    intro: 'Two ways — let the instructor set themselves up, or add them yourself and send a setup email.',
    steps: [
      'Option A — the instructor sets themselves up (easiest): give them your studio’s onboard code (shown next to each studio on the Studios page).',
      '… They go to the sign-in page, choose Existing studios, enter the studio code, pick their name from the list, and enter their email. They then get a link to set their password.',
      'Option B — you add them: go to Instructors (or Users) → Add user. Choose the Instructor role, enter their name and email, and leave the password blank.',
      '… Save, then click Send setup email on their row. They receive a link to set their own password.',
    ],
    notes: [
      'Instructors migrated from another system are already in the list — they just use Option A to claim their account.',
      'Shared front-desk tablet? Instructors can also sign in with the studio code + a personal PIN on the shared-device screen (once PINs have been set).',
    ],
  },
  {
    id: 'instructor-password',
    title: 'Get an instructor set up with a password',
    intro: 'Instructors always choose their OWN password through a one-time setup link — you never see or type it for them.',
    steps: [
      'Trigger the setup link by clicking Send setup email — on the Instructors/Users page, or on the studio/franchise owner screens for owners.',
      'The instructor gets an email with a “Set your password” link.',
      'They click it, choose a password, and are signed straight in. Done — they’re set up.',
    ],
    notes: [
      'The link expires in 72 hours. If it lapses, just click Send setup email again to send a fresh one.',
      'The status on the owners screens shows Invited (email sent, not yet set) or Active (password set).',
      'Until an email provider is connected, the setup link is shown on screen right after you click Send setup email, so you can hand it over directly.',
    ],
  },
]

function Guide({ guide }) {
  return (
    <section
      id={guide.id}
      data-testid={`help-guide-${guide.id}`}
      className="rounded-xl border border-gray-200 bg-white p-5 sm:p-6"
    >
      <h2 className="text-base font-semibold text-gray-900">{guide.title}</h2>
      <p className="mt-1 text-sm text-gray-500">{guide.intro}</p>
      <ol className="mt-4 space-y-2">
        {guide.steps.map((step, i) => (
          <li key={i} className="flex gap-3 text-sm text-gray-700">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-xs font-semibold text-blue-700">
              {i + 1}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      {guide.notes?.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-gray-100 pt-3">
          {guide.notes.map((note, i) => (
            <li key={i} className="text-xs text-gray-500">💡 {note}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

export default function HelpPage() {
  return (
    <AppShell>
      <PageHeader title="Guides & Help" subtitle="How to invite clients and instructors, and set up logins" />
      <div className="mx-auto max-w-3xl px-4 py-4 sm:px-8" data-testid="help-page">
        <nav className="mb-5 flex flex-wrap gap-2">
          {GUIDES.map((g) => (
            <a
              key={g.id}
              href={`#${g.id}`}
              className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 hover:border-blue-400 hover:bg-blue-50"
            >
              {g.title}
            </a>
          ))}
        </nav>
        <div className="space-y-4">
          {GUIDES.map((g) => <Guide key={g.id} guide={g} />)}
        </div>
      </div>
    </AppShell>
  )
}
