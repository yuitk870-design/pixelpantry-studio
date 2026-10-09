self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('push',e=>{let d={};try{d=e.data.json()}catch(_){d={title:'LootDrop',body:e.data&&e.data.text()}}e.waitUntil(self.registration.showNotification(d.title||'LootDrop',{body:d.body||'',icon:'/icon-192.png',badge:'/icon-192.png',tag:d.tag,data:{url:d.url||'/'}}))});
self.addEventListener('notificationclick',e=>{e.notification.close();const url=new URL((e.notification.data&&e.notification.data.url)||'/',self.location.origin).href;e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(l=>{for(const c of l){if('focus' in c){c.navigate(url);return c.focus();}}return clients.openWindow(url);}))});
