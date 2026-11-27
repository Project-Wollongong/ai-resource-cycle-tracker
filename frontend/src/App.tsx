import {
  AuditOutlined,
  BellOutlined,
  BranchesOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
  ImportOutlined,
  LineChartOutlined,
  RadarChartOutlined,
  ReconciliationOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography } from "antd";

import ThemeSwitch from "./components/ThemeSwitch";
import type { MenuProps } from "antd";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import Backtest from "./pages/Backtest";
import HistoricalAnalysis from "./pages/HistoricalAnalysis";
import Positions from "./pages/Positions";
import ProjectDetail from "./pages/ProjectDetail";
import EntityReview from "./pages/EntityReview";
import Ranking from "./pages/Ranking";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import Signals from "./pages/Signals";
import StockDetail from "./pages/StockDetail";
import TradeReviews from "./pages/TradeReviews";
import DataRuns from "./pages/DataRuns";
import VersionReview from "./pages/VersionReview";
import Backfill from "./pages/Backfill";

const { Sider, Content, Footer } = Layout;

/**
 * Grouped by how often a page is opened, not by which subsystem built it.
 *
 * The flat list put "today's board" beside "version-relation review" as peers,
 * which costs attention every single day for the sake of a page used a handful
 * of times a year. Routes are unchanged, so existing links and bookmarks keep
 * working.
 */
const MENU: MenuProps["items"] = [
  {
    key: "grp-daily",
    type: "group",
    label: "每天",
    children: [
      { key: "/", icon: <RadarChartOutlined />, label: <Link to="/">雷达排名</Link> },
      { key: "/positions", icon: <LineChartOutlined />, label: <Link to="/positions">持仓监控</Link> },
      { key: "/signals", icon: <BellOutlined />, label: <Link to="/signals">信号记录</Link> },
    ],
  },
  {
    key: "grp-research",
    type: "group",
    label: "研究",
    children: [
      { key: "/backtest", icon: <ExperimentOutlined />, label: <Link to="/backtest">回测</Link> },
      { key: "/historical-analysis", icon: <FundProjectionScreenOutlined />, label: <Link to="/historical-analysis">历史验证</Link> },
      { key: "/trade-reviews", icon: <ReconciliationOutlined />, label: <Link to="/trade-reviews">交易复盘</Link> },
      { key: "/reports", icon: <FileTextOutlined />, label: <Link to="/reports">日报</Link> },
    ],
  },
  {
    key: "grp-ops",
    type: "group",
    label: "运维",
    children: [
      { key: "/data-runs", icon: <DatabaseOutlined />, label: <Link to="/data-runs">数据运行</Link> },
      { key: "/entity-review", icon: <AuditOutlined />, label: <Link to="/entity-review">实体审核</Link> },
      { key: "/p3/version-review", icon: <BranchesOutlined />, label: <Link to="/p3/version-review">版本关系审核</Link> },
      { key: "/admin/backfill", icon: <ImportOutlined />, label: <Link to="/admin/backfill">历史回填</Link> },
      { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
    ],
  },
];

const NAV_KEYS = MENU.flatMap((group) =>
  group && "children" in group && group.children
    ? group.children.map((child) => String(child!.key))
    : [],
);

/**
 * Which nav entry to highlight for a path.
 *
 * "/" is excluded from prefix matching because it prefixes everything; it is
 * the fallback instead. Detail routes such as /stocks/HAS match no entry and
 * fall back to the ranking page they were reached from.
 */
export function selectedNavKey(pathname: string): string {
  return NAV_KEYS.filter((key) => key !== "/").find((key) => pathname.startsWith(key)) ?? "/";
}

export default function App({ onThemeChange }: { onThemeChange?: (mode: import("./theme").ThemeMode) => void } = {}) {
  const location = useLocation();
  const selected = selectedNavKey(location.pathname);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={200} style={{ background: "var(--sunk)" }}>
        <div style={{ padding: "18px 16px 8px" }}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            Resource Cycle
          </Typography.Title>
          <Typography.Text style={{ fontSize: 12, color: "var(--ink-faint)" }}>
            ASX 资源股投研雷达
          </Typography.Text>
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={MENU} />
        <div style={{ padding: "14px 16px" }}>
          <div className="micro" style={{ marginBottom: 6 }}>外观</div>
          <ThemeSwitch onChange={onThemeChange} />
        </div>
      </Sider>
      <Layout>
        <Content style={{ padding: 20, background: "var(--ground)" }}>
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--line)",
              padding: 20,
              borderRadius: 3,
              minHeight: "100%",
            }}
          >
            <Routes>
              <Route path="/" element={<Ranking />} />
              <Route path="/stocks/:code" element={<StockDetail />} />
              <Route path="/projects/:projectKey" element={<ProjectDetail />} />
              <Route path="/entity-review" element={<EntityReview />} />
              <Route path="/p3/version-review" element={<VersionReview />} />
              <Route path="/admin/backfill" element={<Backfill />} />
              <Route path="/data-runs" element={<DataRuns />} />
              <Route path="/signals" element={<Signals />} />
              <Route path="/positions" element={<Positions />} />
              <Route path="/trade-reviews" element={<TradeReviews />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/historical-analysis" element={<HistoricalAnalysis />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </div>
        </Content>
        <Footer style={{ textAlign: "center", color: "var(--ink-faint)", fontSize: 12 }}>
          仅供研究参考，不构成投资建议 · Research only, not investment advice · Cycle Score 衡量的是资源故事的市场共识强度，不是上涨概率
        </Footer>
      </Layout>
    </Layout>
  );
}
