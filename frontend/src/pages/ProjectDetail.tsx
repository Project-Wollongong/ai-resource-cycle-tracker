import { Alert, Card, Descriptions, Space, Spin, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { ProjectDetail } from "../api/types";

export default function ProjectDetailPage() {
  const { projectKey = "" } = useParams();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.get<ProjectDetail>(`/projects/${encodeURIComponent(projectKey)}`).then(setProject).catch((e) => setError((e as Error).message));
  }, [projectKey]);

  if (error) return <Alert type="error" message={error} />;
  if (!project) return <Spin />;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small" title={project.name} extra={<Link to="/">返回雷达</Link>}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="Project Key">{project.project_key}</Descriptions.Item>
          <Descriptions.Item label="Commodity">{project.commodity || "暂无"}</Descriptions.Item>
          <Descriptions.Item label="状态">{project.active ? "Active" : "Inactive"}</Descriptions.Item>
          <Descriptions.Item label="地区">{project.region || "暂无"}</Descriptions.Item>
          <Descriptions.Item label="司法辖区">{project.jurisdiction || "暂无"}</Descriptions.Item>
          <Descriptions.Item label="阶段">{project.stage || "暂无"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card size="small" title="Ownership / Operator 历史">
        {project.relationships.length === 0 ? <Typography.Text type="secondary">暂无关系记录</Typography.Text> : (
          <Space direction="vertical" style={{ width: "100%" }}>
            {project.relationships.map((relationship) => (
              <Space key={relationship.id} wrap>
                <Tag>{relationship.relationship_type}</Tag>
                <span>Stock #{relationship.stock_id}</span>
                {relationship.ownership_pct != null && <Tag>{relationship.ownership_pct}%</Tag>}
                {relationship.operator_name && <Tag>Operator: {relationship.operator_name}</Tag>}
                <Typography.Text type="secondary">
                  {relationship.effective_from || "起始未知"} → {relationship.effective_to || "当前"}
                </Typography.Text>
              </Space>
            ))}
          </Space>
        )}
      </Card>

      <Card size="small" title={`Asset Units (${project.asset_units.length})`}>
        {project.asset_units.length === 0 ? <Typography.Text type="secondary">暂无 Asset Unit</Typography.Text> : (
          <Space direction="vertical" style={{ width: "100%" }}>
            {project.asset_units.map((asset) => (
              <Card key={asset.id} size="small" type="inner" title={asset.name}>
                <Space wrap>
                  {asset.unit_type && <Tag>{asset.unit_type}</Tag>}
                  {asset.commodity_override && <Tag>Commodity: {asset.commodity_override}</Tag>}
                  {asset.ownership_override_pct != null && <Tag>{asset.ownership_override_pct}% ownership override</Tag>}
                  {asset.operator_override && <Tag>Operator: {asset.operator_override}</Tag>}
                </Space>
              </Card>
            ))}
          </Space>
        )}
      </Card>
    </Space>
  );
}
