import {workspace} from '../workspace.js';

const page = {
  "title": "现场导视图版本",
  "module": "导视图签注",
  "caption": "导视图签注 / 生效图签",
  "detail": "坡道关停后，指向它的现行图签一次性切换为“受阻”，旧版仍可在版本记录中查询。替代入口按原偏好从可通行入口重算匹配；未达门槛则保留受阻提示，重新走测后才能签出替代路线。",
  "path": "/map_notes",
  "columns": [
    {"name": "code", "label": "图签编号"},
    {"name": "state", "label": "状态"},
    {"name": "edition", "label": "图纸版本"},
    {"name": "entrance", "label": "指向入口"},
    {"name": "detour", "label": "线路单"},
    {"name": "legend", "label": "导视文本"},
    {"name": "current", "label": "现行有效"},
    {"name": "recommended", "label": "推荐替代入口"},
    {"name": "basis", "label": "推荐依据"},
  ],
  "layout": "stack",
  "view": "grid",
  "actions": [
    {
      "name": "close_ramp",
      "label": "关停坡道并切换现行图签",
      "path": "/entrances/close-ramp",
      "fields": [
        {"name": "entrance", "label": "关停入口", "kind": "text", "initial": "PK-E2"},
        {"name": "reason", "label": "关停原因", "kind": "text", "initial": "临时围挡封住坡道"}
      ],
      "help": "同一事务把指向该入口的现行图签切为受阻并留存旧版；重复提交不会重复换版。",
      "roles": ["operator", "reviewer"],
      "success": "已关停并切换"
    },
    {
      "name": "publish_map",
      "label": "签出导视图图签",
      "path": "/map_notes/publish-map",
      "fields": [
        {"name": "code", "label": "图签编号", "kind": "text", "initial": "NOTE-11"},
        {"name": "detour", "label": "线路单号", "kind": "text", "initial": "DP-11"},
        {"name": "edition", "label": "版本标记", "kind": "text", "initial": "2026-11-24b"}
      ],
      "help": "复核员签出一条独立图签。坡道已关停的旧提报会被拦下（409）；替代路线须先重算、重新走测，再填新线路单（如 DP-12）。",
      "roles": ["reviewer"],
      "success": "已写入"
    }
  ]
};

export const {title} = page;
export const key = "map_notes";
export async function render(root, role) {
  await workspace(root, role, page);
}
