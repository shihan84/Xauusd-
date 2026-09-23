import MarketDashboard from '../../components/MarketDashboard';
import StrategyLabPanel from '../../components/StrategyLabPanel';
import VcprLevelsPanel from '../../components/VcprLevelsPanel';
import VcprReactionPanel from '../../components/VcprReactionPanel';

export default function DashboardPage() {
  return (
    <>
      <MarketDashboard />
      <StrategyLabPanel />
      <VcprLevelsPanel />
      <VcprReactionPanel />
    </>
  );
}
