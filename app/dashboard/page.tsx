import MarketDashboard from '../../components/MarketDashboard';
import VcprLevelsPanel from '../../components/VcprLevelsPanel';
import VcprReactionAnalytics from '../../components/VcprReactionAnalytics';

export default function DashboardPage() {
  return (
    <>
      <MarketDashboard />
      <VcprLevelsPanel />
      <VcprReactionAnalytics />
    </>
  );
}
