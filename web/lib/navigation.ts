export const navigationGroups = [
  {title:"Library",icon:"◈",links:[
    ["/","Overview"],["/memories","Memories"],["/documents","Documents"],
    ["/knowledge","Knowledge graph"],["/timeline","Timeline"],
  ]},
  {title:"Workspace",icon:"✧",links:[
    ["/intelligence","Intelligence"],["/projects","Projects"],["/agent","Memory Agent"],
  ]},
  {title:"Capture & review",icon:"✦",links:[
    ["/imports","Memory Inbox"],["/connectors","Connectors"],["/approvals","Approvals"],
  ]},
  {title:"System",icon:"⌘",links:[
    ["/system","Health & about"],["/observability","Observability"],
    ["/disaster-recovery","Disaster Recovery"],["/audit","Audit trail"],["/settings","AI, API & OAuth"],
  ]},
];

export function isNavigationPage(pathname:string,href:string) {
  return pathname===href || (href!=="/" && pathname.startsWith(href+"/"));
}

export function navigationGroup(pathname:string) {
  return navigationGroups.find(group=>group.links.some(([href])=>isNavigationPage(pathname,href)));
}
