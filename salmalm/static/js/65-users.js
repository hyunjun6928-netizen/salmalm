  /* ── Users Panel (Multi-tenant) ── */
  window.loadUsers=function(){
    fetch('/api/users',{headers:{'Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')}})
    .then(function(r){return r.json()}).then(function(d){
      if(d.error){document.getElementById('user-list').textContent=d.error;return}
      document.getElementById('mt-toggle').checked=!!d.multi_tenant;
      var sel=document.getElementById('reg-mode');if(sel)sel.value=d.registration_mode||'admin_only';
      var users=d.users||[];
      if(!users.length){document.getElementById('user-list').textContent='No users yet.';return}
      var h='<table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="border-bottom:1px solid var(--border)"><th>User</th><th>Role</th><th>Cost</th><th>Quota (D/M)</th><th>Status</th><th></th></tr>';
      users.forEach(function(u){
        var q=u.quota||{};
        var status=u.enabled?'✅':'⛔';
        h+='<tr style="border-bottom:1px solid var(--border);line-height:2.2">';
        h+='<td>'+u.username+'</td><td>'+u.role+'</td>';
        h+='<td>$'+(u.total_cost||0).toFixed(2)+'</td>';
        h+='<td>$'+(q.current_daily||0).toFixed(2)+'/$'+(q.daily_limit||5).toFixed(0)+' / $'+(q.current_monthly||0).toFixed(2)+'/$'+(q.monthly_limit||50).toFixed(0)+'</td>';
        h+='<td>'+status+'</td>';
        h+='<td>';
        if(u.role!=='admin'){
          var toggleLabel=u.enabled?'Disable':'Enable';
          h+='<button data-action="toggleUser" data-uid="'+u.id+'" data-enabled="'+(!u.enabled)+'" style="font-size:11px;padding:2px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg3);color:var(--text2);cursor:pointer">'+toggleLabel+'</button> ';
          h+='<button data-action="deleteUser" data-username="'+u.username+'" style="font-size:11px;padding:2px 8px;border:1px solid var(--red);border-radius:4px;background:var(--bg3);color:var(--red);cursor:pointer">Delete</button>';
        }
        h+='</td></tr>';
      });
      h+='</table>';
      document.getElementById('user-list').innerHTML=h;
    }).catch(function(e){document.getElementById('user-list').textContent='Error: '+e});
  };
  window.createUser=function(){
    var name=document.getElementById('new-user-name').value.trim();
    var pw=document.getElementById('new-user-pw').value;
    var role=document.getElementById('new-user-role').value;
    if(!name||!pw){alert('Username and password required');return}
    fetch('/api/users/register',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({username:name,password:pw,role:role})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){document.getElementById('new-user-name').value='';document.getElementById('new-user-pw').value='';window.loadUsers()}
      else alert(d.error||'Failed')
    });
  };
  window.toggleUser=function(uid,enabled){
    fetch('/api/users/toggle',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({user_id:uid,enabled:enabled})})
    .then(function(){window.loadUsers()});
  };
  window.deleteUser=function(username){
    if(!confirm('Delete user '+username+'?'))return;
    fetch('/api/users/delete',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({username:username})})
    .then(function(){window.loadUsers()});
  };
  document.getElementById('mt-toggle').addEventListener('change',function(){
    fetch('/api/tenant/config',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({multi_tenant:this.checked})});
  });
  document.getElementById('reg-mode').addEventListener('change',function(){
    fetch('/api/tenant/config',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({registration_mode:this.value})});
  });
