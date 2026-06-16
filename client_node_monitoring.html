// Admin dashboard: poll for updates
(function(){
	async function fetchDashboard(){
		try{
			const res = await fetch('/admin-panel/api/dashboard/');
			if(!res.ok) return;
			const d = await res.json();
			// Update node statuses
			if(Array.isArray(d.server_nodes)){
				d.server_nodes.forEach(n=>{
					const li = document.querySelector(`#node-list li[data-node='${n.id}']`);
					if(li){ li.querySelector('.node-status').textContent = n.is_healthy ? 'Healthy' : 'Down'; }
				});
			}
		}catch(e){ console.warn(e); }
	}

	fetchDashboard();
	setInterval(fetchDashboard, 5000);
})();
