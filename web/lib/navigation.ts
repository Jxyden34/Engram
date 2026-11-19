export const navigationGroups = [
  {title:"Library",icon:"◈",links:[
    ["/","Overview"],["/memories","Memories"],["/documents","Documents"],
    ["/knowledge","Knowledge graph"],["/timeline","Timeline"],
  ]},
  {title:"Workspace",icon:"✧",links:[
    ["/intelligence","Intelligence"],["/projects","Projects"],["/agent","Memory Agent"],["/dreams","Dream Lab"],
  ]},
  {title:"Capture & review",icon:"✦",links:[
    ["/imports","Memory Inbox"],["/connectors","Connectors"],["/approvals","Approvals"],["/notifications","Notifications"],
  ]},
  {title:"System",icon:"⌘",links:[
    ["/system","Health & about"],["/observability","Observability"],
    ["/disaster-recovery","Disaster Recovery"],["/audit","Audit trail"],["/settings","Personal API Gateway"],
    ["/licence","Licence"],["/team","Team workspace"],["/branding","Company branding"],["/handover","Project handover"],["/setup","Setup wizard"],["/reminders","Reminders"],
  ]},
];

export function isNavigationPage(pathname:string,href:string) {
  return pathname===href || (href!=="/" && pathname.startsWith(href+"/"));
}

export function navigationGroup(pathname:string) {
  return navigationGroups.find(group=>group.links.some(([href])=>isNavigationPage(pathname,href)));
}
