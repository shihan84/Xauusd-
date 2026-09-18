import MarketDashboard from '../../components/MarketDashboard';
import VcprLevelsPanel from '../../components/VcprLevelsPanel';
import VcprReactionPanel from '../../components/VcprReactionPanel';

export default function DashboardPage() {
  return (
    <>
      <MarketDashboard />
      <VcprLevelsPanel />
      <VcprReactionPanel />
    </>
  );
}
