import { Link } from 'react-router-dom'
import {
  IconUsersGroup,
  IconLockAccess,
  IconMessages,
  IconCreditCard,
  IconArrowRight,
} from '@tabler/icons-react'
import AppShell from '../components/layout/AppShell'
import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import { APP_NAME } from '../config/brand'

// The default landing page after sign-in. This is a starter kit, so Home
// doubles as a tour: each card below is a subsystem that ships with the
// kit, in plain English, linking straight to the live page that proves it
// works rather than to more documentation.
const SECTIONS = [
  {
    icon: IconUsersGroup,
    title: 'Users & permissions',
    description:
      'Every login has a role, and every role is scoped somewhere in the franchise → studio hierarchy. Admins see everything; a studio owner or manager sees only their own studio; a franchise owner/manager sees only their own franchise.',
    links: [
      { label: 'Users & roles', to: '/admin/users' },
      { label: 'Franchises', to: '/ownership/franchises' },
      { label: 'Studios', to: '/studios' },
    ],
  },
  {
    icon: IconLockAccess,
    title: 'Login & backdoor access',
    description:
      'Three ways in, side by side: a normal email + password login, an admin "act as this user" backdoor for support and testing, and a studio shared-device flow for a front-desk tablet — pick a studio by code, pick a name, enter a PIN.',
    links: [
      { label: 'Sign in', to: '/login' },
      { label: 'Try impersonation from Users', to: '/admin/users' },
      { label: 'Shared-device login', to: '/shared' },
    ],
    note: 'Demo hint: studio code DEMO1, instructor PIN 1234.',
  },
  {
    icon: IconMessages,
    title: 'Communication engine',
    description:
      'A lightweight, built-in way for the platform to talk to its users and back: admin-authored announcements shown once at login (Notes), and a private two-way question thread between any user and an admin (Chat/Questions).',
    links: [
      { label: 'Notes to users', to: '/notes' },
      { label: 'Chat with us', to: '/chat' },
      { label: 'Admin question inbox', to: '/admin/questions' },
    ],
  },
  {
    icon: IconCreditCard,
    title: 'Products & pricing',
    description:
      'A price book of pricing tiers, plus real Stripe billing on top: an admin sets a studio’s contracted price and sends a Stripe checkout link, and a studio owner can review their own billing status.',
    links: [
      { label: 'Pricing tiers', to: '/setup/pricing-tiers' },
      { label: 'Studio billing (admin)', to: '/setup/billing' },
      { label: 'My billing', to: '/billing' },
    ],
  },
]

function SectionCard({ section }) {
  const Icon = section.icon
  return (
    <section
      data-testid={`home-section-${section.title.toLowerCase().replace(/[^a-z]+/g, '-')}`}
      className="rounded-xl border border-gray-200 bg-white p-5 sm:p-6"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <Icon size={20} />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-gray-900">{section.title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-gray-600">{section.description}</p>
        </div>
      </div>

      {section.note && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
          {section.note}
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {section.links.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            data-testid={`home-link-${link.to}`}
            className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
          >
            {link.label}
            <IconArrowRight size={12} className="opacity-60" />
          </Link>
        ))}
      </div>
    </section>
  )
}

export default function HomePage() {
  return (
    <AppShell>
      <PageHeader title="Home" subtitle={`A tour of what ${APP_NAME} ships with`} />
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-4 sm:px-8" data-testid="home-page">
        <div className="rounded-xl border border-blue-100 bg-blue-50/60 px-5 py-4">
          <div className="mb-1 flex items-center gap-2">
            <Badge color="blue">Starter kit</Badge>
          </div>
          <p className="text-sm text-gray-700">
            {APP_NAME} is a store-engine starter: user accounts and roles, a
            franchise → studio hierarchy, a small communication layer, and
            Stripe-backed pricing and billing — all wired together and ready
            to build a real product on top of. Each card below is live; click
            through and try it.
          </p>
        </div>

        {SECTIONS.map((section) => (
          <SectionCard key={section.title} section={section} />
        ))}
      </div>
    </AppShell>
  )
}
