import {
  DatabaseOutlined,
  LockOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";

import {
  listDataDictionary,
  type DataDictionaryEntry,
  type DictionaryValueType,
} from "@/api/dataDictionary";

const { Text, Title } = Typography;

const valueTypeLabels: Record<DictionaryValueType, string> = {
  string: "文本",
  int: "整数",
  float: "小数",
  bool: "布尔",
  json: "JSON",
  secret: "密钥",
};

function displayValue(entry: DataDictionaryEntry) {
  if (entry.is_secret || entry.value_type === "secret") {
    return entry.configured ? "已配置，已隐藏" : "未配置";
  }
  if (!entry.configured) return "空值";
  if (typeof entry.value === "boolean") return entry.value ? "true" : "false";
  if (entry.value === null || entry.value === undefined) return "空值";
  if (typeof entry.value === "object") return JSON.stringify(entry.value);
  return String(entry.value);
}

function formatDate(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function DataDictionaryPage() {
  const [entries, setEntries] = useState<DataDictionaryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [namespace, setNamespace] = useState<string | undefined>();
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setEntries(await listDataDictionary({ limit: 500 }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "数据字典加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const namespaces = useMemo(
    () => [...new Set(entries.map((entry) => entry.namespace))].sort(),
    [entries],
  );
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return entries.filter((entry) => {
      if (namespace && entry.namespace !== namespace) return false;
      if (!term) return true;
      return [entry.namespace, entry.key, entry.description]
        .some((value) => value.toLowerCase().includes(term));
    });
  }, [entries, namespace, search]);

  const columns: ColumnsType<DataDictionaryEntry> = [
    {
      title: "命名空间",
      dataIndex: "namespace",
      width: 150,
      render: (value: string) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: "键",
      dataIndex: "key",
      width: 280,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: "类型",
      dataIndex: "value_type",
      width: 100,
      render: (value: DictionaryValueType) => (
        <Tag icon={value === "secret" ? <LockOutlined /> : <DatabaseOutlined />}>
          {valueTypeLabels[value]}
        </Tag>
      ),
    },
    {
      title: "值",
      key: "value",
      width: 260,
      render: (_, entry) => (
        <Text
          type={entry.is_secret ? "secondary" : undefined}
          ellipsis={{ tooltip: displayValue(entry) }}
        >
          {displayValue(entry)}
        </Text>
      ),
    },
    {
      title: "说明",
      dataIndex: "description",
      ellipsis: true,
      render: (value: string) => value || "-",
    },
    {
      title: "版本",
      dataIndex: "revision",
      width: 84,
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 180,
      render: formatDate,
    },
  ];

  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <Title level={1}>数据字典</Title>
          <Text type="secondary">
            系统配置与敏感凭据的统一索引，密钥值不会在管理端回显。
          </Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
          重新读取
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          closable
          message={error}
          onClose={() => setError(null)}
        />
      )}

      <Card>
        <Space wrap className="dictionary-toolbar">
          <Select
            allowClear
            placeholder="全部命名空间"
            value={namespace}
            onChange={setNamespace}
            options={namespaces.map((value) => ({ value, label: value }))}
            style={{ minWidth: 180 }}
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索键或说明"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ width: 280 }}
          />
          <Text type="secondary">共 {filtered.length} 项</Text>
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: 1180 }}
        />
      </Card>
    </section>
  );
}
