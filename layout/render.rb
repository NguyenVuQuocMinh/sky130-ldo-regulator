# Render ldo_final.gds to PNG with the sky130 layer colours (open_pdks sky130.lyp).
#   klayout_app -b -rd input=... -rd lyp=... -rd png=... [-rd box=x0,y0,x1,y1] [-rd hide=66/13,...] -r render.rb
lv = RBA::LayoutView.new
lv.load_layout($input, true)
lv.load_layer_props($lyp)
lv.max_hier
lv.set_config("background-color", "#ffffff")
lv.set_config("grid-visible", "false")
lv.set_config("text-visible", "true")
if $box
  x0, y0, x1, y1 = $box.split(",").map(&:to_f)
  lv.zoom_box(RBA::DBox.new(x0, y0, x1, y1))
else
  lv.zoom_fit
end
w = ($w || "2400").to_i
h = ($h || "800").to_i
lv.save_image($png, w, h)
puts "wrote #{$png}"
