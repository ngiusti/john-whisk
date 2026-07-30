"""Phone/web dashboard: a small Flask app served from the Pi (LAN-only) that
reuses the voice app's SQLite stores, so edits from a phone and from voice stay
in sync. Run: `python -m john_whisk.web`."""
from flask import Flask, request, jsonify, abort

from john_whisk import (config, db, recipes, grocery, ratings,
                        restrictions, equipment, flavor, nutrition)


def _field(name):
    data = request.get_json(silent=True) or {}
    val = str(data.get(name, "")).strip()
    if not val:
        abort(400, description=f"missing '{name}'")
    return val


def create_app():
    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    # --- grocery ----------------------------------------------------------
    @app.get("/api/grocery")
    def grocery_list():
        return jsonify(items=grocery.items())

    @app.post("/api/grocery")
    def grocery_add():
        grocery.add([_field("item")])
        return jsonify(items=grocery.items())

    @app.post("/api/grocery/remove")
    def grocery_remove():
        grocery.remove([_field("item")])
        return jsonify(items=grocery.items())

    @app.post("/api/grocery/clear")
    def grocery_clear():
        grocery.clear()
        return jsonify(items=[])

    # --- pantry -----------------------------------------------------------
    @app.get("/api/pantry")
    def pantry_list():
        return jsonify(items=db.get_inventory())

    @app.post("/api/pantry")
    def pantry_add():
        db.add_items([{"name": _field("name").lower(), "quantity": None, "unit": None}])
        return jsonify(items=db.get_inventory())

    @app.post("/api/pantry/remove")
    def pantry_remove():
        db.remove_items([_field("name")])
        return jsonify(items=db.get_inventory())

    # --- recipes ----------------------------------------------------------
    @app.get("/api/recipes")
    def recipes_search():
        q = request.args.get("q", "").strip()
        if q:
            hits = recipes.search(q, limit=25)
            return jsonify(results=[{"title": h["title"]} for h in hits], count=recipes.count())
        return jsonify(results=[{"title": t} for t in recipes.list_titles(25)],
                       count=recipes.count())

    @app.get("/api/recipes/view")
    def recipes_view():
        title = request.args.get("title", "").strip()
        r = recipes.find(title) if title else None
        if not r:
            abort(404, description="recipe not found")
        return jsonify(r)

    # --- settings (restrictions / equipment / flavor / ratings) -----------
    @app.get("/api/settings")
    def settings():
        return jsonify(restrictions=restrictions.active(), equipment=equipment.owned(),
                       flavor=flavor.prefs(), favorites=ratings.favorites(),
                       disliked=ratings.disliked())

    def _setting_routes(name, mod):
        @app.post(f"/api/{name}", endpoint=f"{name}_add")
        def _add():
            mod.add([_field("item").lower()])
            return jsonify(ok=True)

        @app.post(f"/api/{name}/remove", endpoint=f"{name}_remove")
        def _remove():
            mod.remove([_field("item").lower()])
            return jsonify(ok=True)

    _setting_routes("restrictions", restrictions)
    _setting_routes("equipment", equipment)
    _setting_routes("flavor", flavor)

    # --- nutrition (today's log + goals) ----------------------------------
    @app.get("/api/nutrition")
    def nutrition_status():
        return jsonify(totals=nutrition.today(), goals=nutrition.goals(),
                       remaining=nutrition.remaining(), entries=nutrition.today_entries())

    @app.post("/api/nutrition/log")
    def nutrition_log_add():
        nutrition.log_food(_field("item"))
        return jsonify(totals=nutrition.today(), entries=nutrition.today_entries())

    @app.post("/api/nutrition/log/remove")
    def nutrition_log_remove():
        data = request.get_json(silent=True) or {}
        try:
            nutrition.remove_log(int(data.get("id")))
        except (TypeError, ValueError):
            abort(400, description="numeric 'id' required")
        return jsonify(totals=nutrition.today(), entries=nutrition.today_entries())

    @app.post("/api/nutrition/goal")
    def nutrition_goal_set():
        data = request.get_json(silent=True) or {}
        field = str(data.get("field", "")).strip().lower()
        try:
            value = float(data.get("value"))
        except (TypeError, ValueError):
            abort(400, description="numeric 'value' required")
        if not nutrition.set_goal(field, value):
            abort(400, description="field must be calories, protein, carbs, or fat")
        return jsonify(goals=nutrition.goals(), remaining=nutrition.remaining())

    @app.errorhandler(400)
    def _bad(e):
        return jsonify(error=str(e.description)), 400

    @app.errorhandler(404)
    def _nf(e):
        return jsonify(error=str(e.description)), 404

    return app


PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>John Whisk</title>
<style>
:root{--bg:#14161a;--card:#1e2229;--fg:#e8eaed;--mut:#9aa0a8;--acc:#c8a24a;--line:#2c313a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.4 system-ui,sans-serif}
header{padding:14px 16px;border-bottom:1px solid var(--line);font-weight:700;letter-spacing:.5px}
header span{color:var(--acc)}
nav{display:flex;position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line)}
nav button{flex:1;padding:12px 4px;background:none;border:0;color:var(--mut);font-size:14px}
nav button.on{color:var(--acc);border-bottom:2px solid var(--acc)}
main{padding:14px;max-width:640px;margin:0 auto}
.row{display:flex;align-items:center;gap:10px;padding:11px 12px;background:var(--card);
border:1px solid var(--line);border-radius:10px;margin-bottom:8px}
.row .t{flex:1}.row .s{color:var(--mut);font-size:13px}
.x{color:var(--mut);background:none;border:0;font-size:20px;padding:0 4px}
.add{display:flex;gap:8px;margin:10px 0 16px}
.add input,.add select{flex:1;padding:11px;background:var(--card);border:1px solid var(--line);
border-radius:10px;color:var(--fg);font-size:16px}
.add button,.btn{padding:11px 16px;background:var(--acc);color:#14161a;border:0;border-radius:10px;
font-weight:700}
h3{color:var(--mut);font-size:13px;text-transform:uppercase;letter-spacing:.5px;margin:18px 0 8px}
.chk{width:22px;height:22px}
.muted{color:var(--mut);text-align:center;padding:20px}
pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:12px}
</style></head><body>
<header>JOHN <span>WHISK</span></header>
<nav id=nav></nav><main id=app></main>
<script>
const A=(p,o)=>fetch(p,o).then(r=>r.json());
const POST=(p,b)=>A(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const el=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstElementChild};
let tab='grocery';
const tabs=[['grocery','Grocery'],['pantry','Pantry'],['recipes','Recipes'],['nutrition','Nutrition'],['settings','Settings']];
function nav(){const n=document.getElementById('nav');n.innerHTML='';
 tabs.forEach(([k,l])=>{const b=el(`<button class="${k==tab?'on':''}">${l}</button>`);
 b.onclick=()=>{tab=k;render()};n.appendChild(b)})}
const app=()=>document.getElementById('app');
function list(items,fmt){const a=app();if(!items.length){a.appendChild(el('<div class=muted>Nothing here yet.</div>'));return}
 items.forEach(it=>a.appendChild(fmt(it)))}

async function render(){nav();const a=app();a.innerHTML='';
 if(tab=='grocery'){
   const {items}=await A('/api/grocery');
   const add=el('<div class=add><input id=gi placeholder="Add to grocery list"><button>Add</button></div>');
   add.querySelector('button').onclick=async()=>{const v=add.querySelector('#gi').value.trim();
     if(v){await POST('/api/grocery',{item:v});render()}};a.appendChild(add);
   list(items,it=>{const r=el(`<div class=row><input type=checkbox class=chk><div class=t>${it}</div></div>`);
     r.querySelector('input').onchange=async()=>{await POST('/api/grocery/remove',{item:it});render()};return r});
 } else if(tab=='pantry'){
   const {items}=await A('/api/pantry');
   const add=el('<div class=add><input id=pi placeholder="Add pantry item"><button>Add</button></div>');
   add.querySelector('button').onclick=async()=>{const v=add.querySelector('#pi').value.trim();
     if(v){await POST('/api/pantry',{name:v});render()}};a.appendChild(add);
   list(items,it=>{const q=it.quantity?`${it.quantity} `:'';const c=it.category?`<span class=s>${it.category}</span>`:'';
     const r=el(`<div class=row><div class=t>${q}${it.name}</div>${c}<button class=x>&times;</button></div>`);
     r.querySelector('.x').onclick=async()=>{await POST('/api/pantry/remove',{name:it.name});render()};return r});
 } else if(tab=='recipes'){
   const add=el('<div class=add><input id=ri placeholder="Search recipes"><button>Search</button></div>');
   const go=async()=>{const q=add.querySelector('#ri').value.trim();
     const {results,count}=await A('/api/recipes?q='+encodeURIComponent(q));
     [...a.querySelectorAll('.res')].forEach(e=>e.remove());
     const h=el(`<h3 class=res>${count} recipes</h3>`);a.appendChild(h);
     results.forEach(x=>{const r=el(`<div class="row res"><div class=t>${x.title}</div></div>`);
       r.onclick=async()=>{const v=await A('/api/recipes/view?title='+encodeURIComponent(x.title));
         alert(v.title+"\\n\\nIngredients: "+v.ingredients+"\\n\\n"+v.steps.map((s,i)=>(i+1)+'. '+s).join('\\n'))};
       a.appendChild(r)})};
   add.querySelector('button').onclick=go;a.appendChild(add);go();
 } else if(tab=='nutrition'){
   const d=await A('/api/nutrition');const g=d.goals,t=d.totals,rem=d.remaining;
   a.appendChild(el('<h3>Today</h3>'));
   [['calories','calories'],['protein','g protein'],['carbs','g carbs'],['fat','g fat']].forEach(([k,label])=>{
     const line=g[k]!=null?`${Math.round(t[k])} / ${Math.round(g[k])} ${label}`:`${Math.round(t[k])} ${label}`;
     const right=g[k]!=null?`<span class=s>${Math.round(rem[k])} left</span>`:'';
     a.appendChild(el(`<div class=row><div class=t>${line}</div>${right}</div>`))});
   const add=el('<div class=add><input id=ni placeholder="Log a food, e.g. two eggs"><button>Log</button></div>');
   add.querySelector('button').onclick=async()=>{const v=add.querySelector('#ni').value.trim();
     if(v){await POST('/api/nutrition/log',{item:v});render()}};a.appendChild(add);
   a.appendChild(el('<h3>Logged today</h3>'));
   if(!d.entries.length)a.appendChild(el('<div class=muted>Nothing logged yet.</div>'));
   d.entries.forEach(e=>{const r=el(`<div class=row><div class=t>${e.food}</div><span class=s>${Math.round(e.calories)} cal</span><button class=x>&times;</button></div>`);
     r.querySelector('.x').onclick=async()=>{await POST('/api/nutrition/log/remove',{id:e.id});render()};a.appendChild(r)});
   a.appendChild(el('<h3>Daily goals</h3>'));
   [['calories','Calories'],['protein','Protein (g)'],['carbs','Carbs (g)'],['fat','Fat (g)']].forEach(([k,label])=>{
     const cur=g[k]!=null?g[k]:'';
     const row=el(`<div class=add><input id=goal_${k} type=number placeholder="${label}" value="${cur}"><button>Set</button></div>`);
     row.querySelector('button').onclick=async()=>{const v=row.querySelector('#goal_'+k).value.trim();
       if(v!==''){await POST('/api/nutrition/goal',{field:k,value:parseFloat(v)});render()}};a.appendChild(row)});
 } else {
   const s=await A('/api/settings');
   const sec=(title,name,items,opts)=>{a.appendChild(el(`<h3>${title}</h3>`));
     const add=el(`<div class=add>${opts?`<select id=${name}s>${opts.map(o=>`<option>${o}</option>`).join('')}</select>`:`<input id=${name}s placeholder="Add">`}<button>Add</button></div>`);
     add.querySelector('button').onclick=async()=>{const v=add.querySelector('#'+name+'s').value.trim();
       if(v){await POST('/api/'+name,{item:v});render()}};a.appendChild(add);
     items.forEach(it=>{const r=el(`<div class=row><div class=t>${it}</div><button class=x>&times;</button></div>`);
       r.querySelector('.x').onclick=async()=>{await POST('/api/'+name+'/remove',{item:it});render()};a.appendChild(r)})};
   sec('Dietary restrictions','restrictions',s.restrictions,['dairy','gluten','nuts','eggs','shellfish','fish','soy','pork','vegetarian','vegan']);
   sec('Equipment','equipment',s.equipment,['blender','food processor','slow cooker','air fryer','grill','oven','microwave','pressure cooker','stand mixer','waffle iron']);
   sec('Flavor preferences','flavor',s.flavor);
   a.appendChild(el('<h3>Favorites</h3>'));list(s.favorites.length?s.favorites:[], t=>el(`<div class=row><div class=t>${t}</div></div>`));
   if(s.favorites.length==0)a.appendChild(el('<div class=muted>No favorites yet.</div>'));
 }}
render();
</script></body></html>"""


if __name__ == "__main__":
    create_app().run(host=config.WEB_HOST, port=config.WEB_PORT)
