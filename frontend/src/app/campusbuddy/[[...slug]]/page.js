"use client";

import { usePathname, useRouter } from "next/navigation";

import CampusBuddyShell from "../../../features/campusbuddy/components/CampusBuddyShell";
import CampusBuddyChat from "../../../features/campusbuddy/pages/CampusBuddyChat";
import CampusBuddyHome from "../../../features/campusbuddy/pages/CampusBuddyHome";
import CommitteeDashboard from "../../../features/campusbuddy/pages/CommitteeDashboard";
import CommitteeEscalation from "../../../features/campusbuddy/pages/CommitteeEscalation";
import Groups from "../../../features/campusbuddy/pages/Groups";
import PeopleConnector from "../../../features/campusbuddy/pages/PeopleConnector";
import TrustDashboard from "../../../features/campusbuddy/pages/TrustDashboard";

const campusBuddyRoutes = {
  "/campusbuddy": CampusBuddyHome,
  "/campusbuddy/chat": CampusBuddyChat,
  "/campusbuddy/trust-dashboard": TrustDashboard,
  "/campusbuddy/connect": PeopleConnector,
  "/campusbuddy/groups": Groups,
  "/campusbuddy/escalation": CommitteeEscalation,
  "/campusbuddy/committee-dashboard": CommitteeDashboard,
};

export default function CampusBuddyRoute() {
  const pathname = usePathname();
  const router = useRouter();
  const normalizedPath = pathname !== "/" ? pathname.replace(/\/$/, "") : pathname;
  const CampusBuddyPage = campusBuddyRoutes[normalizedPath] || CampusBuddyHome;

  function navigate(nextPath) {
    router.push(nextPath);
  }

  return (
    <CampusBuddyShell path={normalizedPath} navigate={navigate}>
      <CampusBuddyPage navigate={navigate} />
    </CampusBuddyShell>
  );
}
