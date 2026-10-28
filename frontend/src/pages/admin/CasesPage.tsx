import { Button, DatePicker, Pagination, Select } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { ArrowRight, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { listCases, type CaseRecord, type CaseStatus } from "@/api/cases";

type StatusFilter = CaseStatus | "all";
type DateRange = [Dayjs, Dayjs] | null;

function dateParam(value: string | null) {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) && dayjs(value).isValid() ? value : "";
}

export default function AdminCasesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(8);
  const [total, setTotal] = useState(0);

  const requestedStatus = searchParams.get("status");
  const status: StatusFilter = requestedStatus && requestedStatus in statusText ? requestedStatus as CaseStatus : "all";
  const from = dateParam(searchParams.get("from"));
  const to = dateParam(searchParams.get("to"));
  const dateRange: DateRange = from && to ? [dayjs(from), dayjs(to)] : null;
  const hasFilters = status !== "all" || Boolean(from || to);
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listCases({
      page,
      page_size: pageSize,
      status: status === "all" ? undefined : status,
      from,
      to,
    })
      .then((result) => {
        setTotal(result.total);
        setCases(result.items);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "病例记录加载失败"),
      )
      .finally(() => setLoading(false));
  }, [from, page, pageSize, status, to]);

  function updateFilters(next: Partial<Record<"status" | "from" | "to", string>>) {
    const params = new URLSearchParams(searchParams);
    Object.entries(next).forEach(([key, value]) => {
      if (!value || value === "all") params.delete(key);
      else params.set(key, value);
    });
    setSearchParams(params, { replace: true });
    setPage(1);
  }

  function changeDateRange(dates: [Dayjs | null, Dayjs | null] | null) {
    const [start, end] = dates ?? [null, null];
    updateFilters({
      from: start?.format("YYYY-MM-DD") ?? "",
      to: end?.format("YYYY-MM-DD") ?? "",
    });
  }

  return (
    <section className="page">
      <div className="page-heading"><div><h1>病例审计</h1><p className="page-lead">查看病例处理与复核状态。</p></div></div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="case-filters">
        <Select<StatusFilter>
          value={status}
          onChange={(value) => updateFilters({ status: value })}
          options={[
            { value: "all", label: "全部状态" },
            ...Object.entries(statusText).map(([value, label]) => ({ value: value as CaseStatus, label })),
          ]}
          aria-label="按病例状态筛选"
        />
        <DatePicker.RangePicker
          classNames={{ popup: { root: "case-date-range-popup" } }}
          value={dateRange}
          onChange={changeDateRange}
          allowClear
          placeholder={["更新开始日期", "更新结束日期"]}
          aria-label="按更新时间筛选"
        />
        {hasFilters && (
          <Button icon={<RotateCcw size={15} />} onClick={() => updateFilters({ status: "", from: "", to: "" })}>
            重置
          </Button>
        )}
      </div>
      <div className="case-table">
        {cases.map((item) => (
          <Link to={`/admin/cases/${item.id}`} key={item.id}>
            <div><strong>{item.complaint}</strong><small>{item.owner_name || "未分配医生"} · {item.patient_age} 岁 · 建档 {new Date(item.created_at).toLocaleString("zh-CN")}</small></div>
            <span className={`status ${item.status}`}>{statusText[item.status]}</span><ArrowRight size={16} />
          </Link>
        ))}
        {!loading && !error && total === 0 && (
          <div className="empty-state">
            <p>{hasFilters ? "没有符合筛选条件的病例" : "暂无病例记录"}</p>
            {hasFilters && <span>请调整状态或更新时间范围。</span>}
          </div>
        )}
      </div>
      {total > 0 && (
        <Pagination
          className="case-list-pagination"
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger={total > 8}
          pageSizeOptions={[8, 16, 32]}
          showTotal={(total) => `共 ${total} 例`}
          onChange={(nextPage, nextPageSize) => {
            const pageSizeChanged = nextPageSize !== pageSize;
            setPageSize(nextPageSize);
            setPage(pageSizeChanged ? 1 : nextPage);
          }}
        />
      )}
    </section>
  );
}

const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};
