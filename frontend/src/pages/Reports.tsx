import { Alert, Card, Col, List, Row, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { DailyReport, ReportContent } from "../api/types";
import LabelTag from "../components/LabelTag";
import Pct from "../components/Pct";

type ReportAnnouncement = ReportContent["announcements"][number];

export default function Reports() {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [selected, setSelected] = useState<DailyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await api.get<DailyReport[]>("/reports?limit=30");
      setReports(list);
      setSelected(list[0] ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <Alert type="error" message={error} />;

  const content = selected?.content;

  return (
    <div>
      <Typography.Title level={4}>Daily Reports</Typography.Title>
      <Row gutter={16}>
        <Col span={5}>
          <List
            size="small"
            bordered
            dataSource={reports}
            renderItem={(r) => (
              <List.Item
                onClick={() => setSelected(r)}
                style={{
                  cursor: "pointer",
                  background: selected?.report_date === r.report_date ? "#e6f4ff" : undefined,
                }}
              >
                <Space>
                  {r.report_date}
                  {r.pushed ? <Tag color="green">Pushed</Tag> : <Tag>Not pushed</Tag>}
                </Space>
              </List.Item>
            )}
          />
        </Col>
        <Col span={19}>
          {content ? (
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              {content.source_degraded.length > 0 && (
                <Alert type="warning" message={`Announcement source degraded: ${content.source_degraded.join(", ")}`} />
              )}
              <Card size="small" title="Top Cycle Scores">
                <List
                  size="small"
                  dataSource={content.top}
                  renderItem={(t, i) => (
                    <List.Item>
                      <Space>
                        <span style={{ width: 20, color: "#999" }}>{i + 1}</span>
                        <Link to={`/stocks/${t.code}`}>
                          <b>{t.code}</b>
                        </Link>
                        <span>{t.name}</span>
                        <Tag>{t.commodity}</Tag>
                        <b>{t.cycle_score}</b>
                        <LabelTag label={t.label} />
                        <Pct value={t.day_change_pct} />
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>
              <Card size="small" title={`Signals (${content.signals.length})`}>
                {content.signals.length ? (
                  <List
                    size="small"
                    dataSource={content.signals}
                    renderItem={(s) => (
                      <List.Item>
                        <Space>
                          <Link to={`/stocks/${s.code}`}>{s.code}</Link>
                          <Tag color="purple">{s.type}</Tag>
                          <LabelTag label={s.label} />
                          <span>{s.reason}</span>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Typography.Text type="secondary">No signals today</Typography.Text>
                )}
              </Card>
              <Card size="small" title="Key Announcements">
                {content.announcements.length ? (
                  <List
                    size="small"
                    dataSource={content.announcements}
                    renderItem={(a) => (
                      <List.Item>
                        <AnnouncementItem announcement={a} />
                      </List.Item>
                    )}
                  />
                ) : (
                  <Typography.Text type="secondary">None</Typography.Text>
                )}
              </Card>
              {content.movers.length > 0 && (
                <Card size="small" title="Movers >= 8%">
                  <Space wrap>
                    {content.movers.map((m) => (
                      <span key={m.code}>
                        <Link to={`/stocks/${m.code}`}>{m.code}</Link> <Pct value={m.day_change_pct} />
                      </span>
                    ))}
                  </Space>
                </Card>
              )}
              <Typography.Text type="secondary" italic>
                {content.disclaimer}
              </Typography.Text>
            </Space>
          ) : (
            <Alert type="info" message="No daily report yet. Run the pipeline from Settings first." />
          )}
        </Col>
      </Row>
    </div>
  );
}

function AnnouncementItem({ announcement: a }: { announcement: ReportAnnouncement }) {
  const hasContext = a.quality || a.materiality || a.assessment || a.grade_thickness != null;
  return (
    <Space direction="vertical" size={4} style={{ width: "100%" }}>
      <Space wrap>
        <Link to={`/stocks/${a.code}`}>{a.code}</Link>
        <Tag>{a.type}</Tag>
        {a.price_sensitive && <Tag color="red">PS</Tag>}
        <a href={a.url} target="_blank" rel="noreferrer">
          {a.headline}
        </a>
      </Space>
      {hasContext && (
        <Space wrap>
          {a.quality && <Tag color={a.quality === "insufficient_history" ? "warning" : "blue"}>quality: {a.quality}</Tag>}
          {a.materiality && (
            <Tag
              color={
                a.materiality === "high"
                  ? "red"
                  : a.materiality === "medium"
                    ? "orange"
                    : a.materiality === "insufficient_history"
                      ? "warning"
                      : "default"
              }
            >
              materiality: {a.materiality}
            </Tag>
          )}
          {a.grade_thickness != null && <Tag>GT {a.grade_thickness}</Tag>}
          {a.assessment && <Typography.Text type="secondary">{a.assessment}</Typography.Text>}
        </Space>
      )}
    </Space>
  );
}
