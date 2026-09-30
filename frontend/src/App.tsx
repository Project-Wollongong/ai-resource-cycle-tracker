import {
  AuditOutlined,
  BellOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
  LineChartOutlined,
  RadarChartOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography } from "antd";
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

const MENU = [
  { key: "/data-runs", icon: <SettingOutlined />, label: <Link to="/data-runs">数据运行</Link> },
  { key: "/historical-analysis", icon: <FundProjectionScreenOutlined />, label: <Link to="/historical-analysis">历史验证</Link> },
  { key: "/", icon: <RadarChartOutlined />, label: <Link to="/">雷达排名</Link> },
  { key: "/signals", icon: <BellOutlined />, label: <Link to="/signals">信号记录</Link> },
  { key: "/positions", icon: <LineChartOutlined />, label: <Link to="/positions">Position Monitor</Link> },
  { key: "/trade-reviews", icon: <AuditOutlined />, label: <Link to="/trade-reviews">Trade Reviews</Link> },
  { key: "/backtest", icon: <ExperimentOutlined />, label: <Link to="/backtest">回测</Link> },
  { key: "/reports", icon: <FileTextOutlined />, label: <Link to="/reports">日报</Link> },
  { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
  { key: "/entity-review", icon: <AuditOutlined />, label: <Link to="/entity-review">实体审核</Link> },
  { key: "/p3/version-review", icon: <AuditOutlined />, label: <Link to="/p3/version-review">版本关系审核</Link> },
  { key: "/admin/backfill", icon: <SettingOutlined />, label: <Link to="/admin/backfill">历史回填</Link> },
];

export default function App() {
  const location = useLocation();
  const selected = MENU.find((m) => m.key !== "/" && location.pathname.startsWith(m.key))?.key ?? "/";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={200}>
        <div style={{ padding: "18px 16px 8px" }}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            Resource Cycle
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            ASX 资源股投研雷达
          </Typography.Text>
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={MENU} />
      </Sider>
      <Layout>
        <Content style={{ padding: 20, background: "#f5f5f5" }}>
          <div style={{ background: "#fff", padding: 20, borderRadius: 8, minHeight: "100%" }}>
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
        <Footer style={{ textAlign: "center", color: "#999", fontSize: 12 }}>
          仅供研究参考，不构成投资建议 · Research only, not investment advice · Cycle Score 衡量的是资源故事的市场共识强度，不是上涨概率
        </Footer>
      </Layout>
    </Layout>
  );
}
