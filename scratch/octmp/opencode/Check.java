public class Check {
    public static void main(String[] a) {
        ResistorColorTrio r = new ResistorColorTrio();
        check(r, "33 ohms", "orange","orange","black");
        check(r, "680 ohms", "blue","grey","brown");
        check(r, "2 kiloohms", "red","black","red");
        check(r, "51 kiloohms", "green","brown","orange");
        check(r, "470 kiloohms", "yellow","violet","yellow");
        check(r, "67 megaohms", "blue","violet","blue");
        check(r, "0 ohms", "black","black","black");
        check(r, "99 gigaohms", "white","white","white");
        check(r, "8 ohms", "black","grey","black");
        check(r, "650 kiloohms", "blue","green","yellow","orange");
        System.out.println("ALL PASS");
    }
    static void check(ResistorColorTrio r, String expected, String... colors) {
        String actual = r.label(colors);
        if (!expected.equals(actual)) throw new AssertionError("expected " + expected + " got " + actual);
    }
}
