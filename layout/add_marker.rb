# KLayout batch script: copy the Electric GDS, then
#  1. add the poly_rs marker (66/13) over the body of every xhigh_po unit
#     (cell rxh). Electric's skywater130 technology has no poly_rs layer;
#     without it neither the DRC nor the LVS deck sees a precision resistor.
#  2. add pin labels (met3 label layer 70/5) at the top-cell export points,
#     which Electric's GDS writer does not emit.
#   klayout_app -b -rd input=in.gds -rd output=out.gds -rd body=4.27 -rd width=0.35
#               -rd labels="vin,45.45,35.2;gnd,-20.5,-3.6" -r add_marker.rb
ly = RBA::Layout.new
ly.read($input)
c = ly.cell("rxh")
raise "cell rxh not found" unless c
hb = $body.to_f / 2.0
hw = $width.to_f / 2.0
c.shapes(ly.layer(66, 13)).insert(RBA::DBox.new(-hw, -hb, hw, hb))
puts "poly_rs added: #{2 * hw} x #{2 * hb} um in rxh"

top = ly.cell("ldo")
raise "cell ldo not found" unless top
lbl = ly.layer(70, 5)
($labels || "").split(";").each do |item|
  name, x, y = item.split(",")
  top.shapes(lbl).insert(RBA::DText.new(name, RBA::DTrans.new(x.to_f, y.to_f)))
  puts "label #{name} at (#{x}, #{y}) on met3"
end
ly.write($output)
puts "-> #{$output}"
