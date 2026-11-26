import {workspace} from '../workspace.js';

const page = {
  "title": "入口现场勘验",
  "module": "入口设施核验",
  "caption": "入口设施核验",
  "detail": "坡道通行能力由现场见证更新。把“坡道通行”选为“否”即关停该坡道：同一事务把指向它的现行图签切换为受阻，重试不重复换版。图签发布前会再次核对当前可通行条件。",
  "path": "/entrances",
  "columns": [
    {"name": "code", "label": "编号"},
    {"name": "park", "label": "口袋公园"},
    {"name": "ramp", "label": "坡道通行"},
    {"name": "tags", "label": "障碍标记"},
    {"name": "condition", "label": "核验状态"},
    {"name": "version", "label": "状态版本"}
  ],
  "layout": "split",
  "view": "grid",
  "actions": [
    {
      "name": "inspect",
      "label": "确认入口当前状态",
      "path": "/entrances/inspect",
      "fields": [
        {"name": "entrance", "label": "入口", "kind": "text", "initial": "PK-E2"},
        {"name": "ramp", "label": "坡道通行（否=关停）", "kind": "bool", "initial": false}
      ],
      "help": "维护人员以现场踏勘为准更新坡道状态；由通行改为关停会批量切换现行图签。",
      "roles": ["operator", "reviewer"],
      "success": "已写入"
    },
    {
      "name": "close_ramp_idem",
      "label": "关停坡道（幂等，不重复换版）",
      "path": "/entrances/close-ramp",
      "fields": [
        {"name": "entrance", "label": "入口", "kind": "text", "initial": "PK-E2"},
        {"name": "reason", "label": "关停原因", "kind": "text", "initial": "围挡封住坡道"}
      ],
      "help": "重复关停只回读已切换结果，不会再生成新版本。",
      "roles": ["operator", "reviewer"],
      "success": "已关停"
    }
  ]
};

export const {title} = page;
export const key = "entrances";
export async function render(root, role) {
  await workspace(root, role, page);
}
